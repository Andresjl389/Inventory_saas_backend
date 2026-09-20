"""The single place where stock changes.

Sales, purchases, transfers and manual adjustments all funnel through
`apply_movement`, so the ledger entry and the cached quantity are written
together, under the same row lock, inside the caller's transaction. Nothing
else in the codebase is allowed to write `product_stock`.
"""

import uuid
from decimal import Decimal

from app.domain.inventory.entities.product_stock import ProductStock
from app.domain.inventory.entities.stock_movement import (
    MovementType,
    ReferenceType,
    StockMovement,
)
from app.domain.inventory.repositories.stock_repository import (
    StockMovementRepository,
    StockRepository,
)


class StockService:
    def __init__(self, stock: StockRepository, movements: StockMovementRepository) -> None:
        self._stock = stock
        self._movements = movements

    async def apply_movement(
        self,
        *,
        company_id: uuid.UUID,
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        delta: Decimal,
        movement_type: MovementType,
        reference_type: ReferenceType = ReferenceType.MANUAL,
        reference_id: uuid.UUID | None = None,
        notes: str | None = None,
        created_by: uuid.UUID | None = None,
        allow_negative: bool = False,
    ) -> ProductStock:
        # Lock first, then decide: reading the quantity before the lock would
        # let a concurrent transaction invalidate the check.
        stock = await self._stock.lock_for_update(company_id, product_id, warehouse_id)
        stock.apply(delta, allow_negative=allow_negative)
        saved = await self._stock.save(stock)

        await self._movements.add(
            StockMovement(
                company_id=company_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                movement_type=movement_type,
                quantity=delta,
                reference_type=reference_type,
                reference_id=reference_id,
                notes=notes,
                created_by=created_by,
            )
        )
        return saved
