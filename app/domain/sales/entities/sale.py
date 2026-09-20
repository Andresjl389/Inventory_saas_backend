"""Sale aggregate: the sale header plus its items.

Totals are always derived from the items -- never accepted from the client --
so a request cannot ask to be charged a different amount than its lines add up
to. The header columns exist because reports read them constantly.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.domain.sales.exceptions import (
    EmptySaleError,
    InvalidSaleItemError,
    InvalidSaleTransitionError,
)
from app.domain.shared.entities import BaseEntity, TenantEntity
from app.domain.shared.money import ZERO, money, quantity


class SaleStatus(StrEnum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


@dataclass(kw_only=True)
class SaleItem(BaseEntity):
    company_id: uuid.UUID
    sale_id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal = ZERO
    tax: Decimal = ZERO
    total: Decimal = ZERO

    def __post_init__(self) -> None:
        self.quantity = quantity(self.quantity)
        self.unit_price = money(self.unit_price)
        self.discount = money(self.discount)
        self.tax = money(self.tax)

        if self.quantity <= 0:
            raise InvalidSaleItemError("Item quantity must be greater than zero")
        if self.unit_price < 0:
            raise InvalidSaleItemError("Item unit price cannot be negative")
        if self.discount < 0 or self.tax < 0:
            raise InvalidSaleItemError("Item discount and tax cannot be negative")

        self.total = self.compute_total()
        if self.total < 0:
            raise InvalidSaleItemError("Item discount cannot exceed its gross amount")

    @property
    def gross(self) -> Decimal:
        return money(self.quantity * self.unit_price)

    def compute_total(self) -> Decimal:
        return money(self.gross - self.discount + self.tax)


@dataclass(kw_only=True)
class Sale(TenantEntity):
    warehouse_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    status: SaleStatus = SaleStatus.DRAFT
    subtotal: Decimal = ZERO
    discount: Decimal = ZERO
    tax: Decimal = ZERO
    total: Decimal = ZERO
    notes: str | None = None
    created_by: uuid.UUID | None = None
    items: list[SaleItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.recalculate_totals()

    def recalculate_totals(self) -> None:
        self.subtotal = money(sum((item.gross for item in self.items), ZERO))
        self.discount = money(sum((item.discount for item in self.items), ZERO))
        self.tax = money(sum((item.tax for item in self.items), ZERO))
        self.total = money(self.subtotal - self.discount + self.tax)

    def require_items(self) -> None:
        if not self.items:
            raise EmptySaleError()

    @property
    def affects_stock(self) -> bool:
        """Only a COMPLETED sale has taken stock out of the warehouse."""
        return self.status is SaleStatus.COMPLETED

    def complete(self) -> None:
        if self.status is not SaleStatus.DRAFT:
            raise InvalidSaleTransitionError(
                f"Only a DRAFT sale can be completed (this one is {self.status.value})"
            )
        self.require_items()
        self.status = SaleStatus.COMPLETED
        self.touch()

    def cancel(self) -> None:
        if self.status not in (SaleStatus.DRAFT, SaleStatus.COMPLETED):
            raise InvalidSaleTransitionError(f"A {self.status.value} sale cannot be cancelled")
        self.status = SaleStatus.CANCELLED
        self.touch()

    def refund(self) -> None:
        if self.status is not SaleStatus.COMPLETED:
            raise InvalidSaleTransitionError(
                f"Only a COMPLETED sale can be refunded (this one is {self.status.value})"
            )
        self.status = SaleStatus.REFUNDED
        self.touch()
