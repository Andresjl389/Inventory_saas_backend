"""Denormalised current stock, one row per (company, product, warehouse).

It is a cache of the movement ledger, kept in the same transaction as the
movements that change it, so the two can never disagree.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.domain.inventory.exceptions import InsufficientStockError
from app.domain.shared.entities import TenantEntity


@dataclass(kw_only=True)
class ProductStock(TenantEntity):
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: Decimal = Decimal("0")

    def apply(self, delta: Decimal, *, allow_negative: bool = False) -> None:
        new_quantity = self.quantity + delta
        if new_quantity < 0 and not allow_negative:
            raise InsufficientStockError(
                "Not enough stock for this operation",
                details={
                    "product_id": str(self.product_id),
                    "warehouse_id": str(self.warehouse_id),
                    "available": str(self.quantity),
                    "requested": str(abs(delta)),
                },
            )
        self.quantity = new_quantity
        self.touch()
