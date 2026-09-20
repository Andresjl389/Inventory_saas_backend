"""Stock movements: the append-only ledger behind every stock figure.

`quantity` is the **signed delta** applied to the stock of one product in one
warehouse. Storing the sign (rather than a magnitude plus a type) buys a single
invariant that is cheap to assert and hard to fake:

    product_stock.quantity == SUM(stock_movements.quantity)

Every movement type except ADJUSTMENT has a fixed direction, enforced here.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.inventory.exceptions import InvalidMovementError
from app.domain.shared.entities import BaseEntity, utc_now


class MovementType(StrEnum):
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    RETURN = "RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"

    @property
    def direction(self) -> int:
        """+1 adds stock, -1 removes it, 0 means the sign is free."""
        return {
            MovementType.PURCHASE: 1,
            MovementType.RETURN: 1,
            MovementType.TRANSFER_IN: 1,
            MovementType.SALE: -1,
            MovementType.TRANSFER_OUT: -1,
            MovementType.ADJUSTMENT: 0,
        }[self]


class ReferenceType(StrEnum):
    SALE = "SALE"
    PURCHASE = "PURCHASE"
    TRANSFER = "TRANSFER"
    MANUAL = "MANUAL"


@dataclass(kw_only=True)
class StockMovement(BaseEntity):
    company_id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    movement_type: MovementType
    quantity: Decimal
    reference_type: ReferenceType = ReferenceType.MANUAL
    reference_id: uuid.UUID | None = None
    notes: str | None = None
    created_by: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.quantity == 0:
            raise InvalidMovementError("A stock movement cannot have quantity zero")

        direction = self.movement_type.direction
        if direction and (self.quantity > 0) != (direction > 0):
            sign = "positive" if direction > 0 else "negative"
            raise InvalidMovementError(
                f"{self.movement_type.value} movements must carry a {sign} quantity"
            )

    # Movements are immutable once written; `updated_at` only exists because it
    # comes from BaseEntity, and it always equals created_at.
    def touch(self) -> None:
        self.updated_at = self.created_at or utc_now()
