import uuid
from typing import Protocol

from app.domain.inventory.entities.product_stock import ProductStock
from app.domain.inventory.entities.stock_movement import StockMovement
from app.domain.shared.pagination import Page, PaginatedResult


class StockRepository(Protocol):
    async def lock_for_update(
        self, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID
    ) -> ProductStock:
        """Return the stock row, creating it at zero if absent, holding a row
        lock until the transaction ends.

        This is what stops two concurrent sales from overselling the same unit
        (BACKEND.md section 29)."""
        ...

    async def get(
        self, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID
    ) -> ProductStock | None: ...

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        only_non_zero: bool = False,
    ) -> PaginatedResult[ProductStock]: ...

    async def save(self, stock: ProductStock) -> ProductStock: ...


class StockMovementRepository(Protocol):
    async def add(self, movement: StockMovement) -> StockMovement: ...

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        reference_id: uuid.UUID | None = None,
    ) -> PaginatedResult[StockMovement]: ...
