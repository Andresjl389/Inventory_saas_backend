"""Purchase aggregate: mirror image of a sale -- it puts stock in rather than
taking it out, and its lines carry a unit *cost* instead of a price."""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.domain.purchases.exceptions import (
    EmptyPurchaseError,
    InvalidPurchaseItemError,
    InvalidPurchaseTransitionError,
)
from app.domain.shared.entities import BaseEntity, TenantEntity
from app.domain.shared.money import ZERO, money, quantity


class PurchaseStatus(StrEnum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass(kw_only=True)
class PurchaseItem(BaseEntity):
    company_id: uuid.UUID
    purchase_id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal
    unit_cost: Decimal
    discount: Decimal = ZERO
    tax: Decimal = ZERO
    total: Decimal = ZERO

    def __post_init__(self) -> None:
        self.quantity = quantity(self.quantity)
        self.unit_cost = money(self.unit_cost)
        self.discount = money(self.discount)
        self.tax = money(self.tax)

        if self.quantity <= 0:
            raise InvalidPurchaseItemError("Item quantity must be greater than zero")
        if self.unit_cost < 0:
            raise InvalidPurchaseItemError("Item unit cost cannot be negative")
        if self.discount < 0 or self.tax < 0:
            raise InvalidPurchaseItemError("Item discount and tax cannot be negative")

        self.total = money(self.gross - self.discount + self.tax)
        if self.total < 0:
            raise InvalidPurchaseItemError("Item discount cannot exceed its gross amount")

    @property
    def gross(self) -> Decimal:
        return money(self.quantity * self.unit_cost)

    @property
    def net_unit_cost(self) -> Decimal:
        """Cost per unit after discount and tax -- what the product's
        cost_price is refreshed to when the purchase is completed."""
        return money(self.total / self.quantity)


@dataclass(kw_only=True)
class Purchase(TenantEntity):
    warehouse_id: uuid.UUID
    supplier_id: uuid.UUID | None = None
    status: PurchaseStatus = PurchaseStatus.DRAFT
    subtotal: Decimal = ZERO
    discount: Decimal = ZERO
    tax: Decimal = ZERO
    total: Decimal = ZERO
    notes: str | None = None
    created_by: uuid.UUID | None = None
    items: list[PurchaseItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.recalculate_totals()

    def recalculate_totals(self) -> None:
        self.subtotal = money(sum((item.gross for item in self.items), ZERO))
        self.discount = money(sum((item.discount for item in self.items), ZERO))
        self.tax = money(sum((item.tax for item in self.items), ZERO))
        self.total = money(self.subtotal - self.discount + self.tax)

    def require_items(self) -> None:
        if not self.items:
            raise EmptyPurchaseError()

    @property
    def affects_stock(self) -> bool:
        return self.status is PurchaseStatus.COMPLETED

    def complete(self) -> None:
        if self.status is not PurchaseStatus.DRAFT:
            raise InvalidPurchaseTransitionError(
                f"Only a DRAFT purchase can be completed (this one is {self.status.value})"
            )
        self.require_items()
        self.status = PurchaseStatus.COMPLETED
        self.touch()

    def cancel(self) -> None:
        if self.status not in (PurchaseStatus.DRAFT, PurchaseStatus.COMPLETED):
            raise InvalidPurchaseTransitionError(
                f"A {self.status.value} purchase cannot be cancelled"
            )
        self.status = PurchaseStatus.CANCELLED
        self.touch()
