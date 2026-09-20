import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.inventory.entities.product_stock import ProductStock
from app.domain.inventory.entities.stock_movement import StockMovement
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.inventory import ProductStockModel, StockMovementModel
from app.infrastructure.database.repositories.mappers import (
    product_stock_to_domain,
    stock_movement_to_domain,
)


class SqlAlchemyStockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_for_update(
        self, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID
    ) -> ProductStock:
        """Create-if-absent, then take a row lock held until COMMIT.

        The INSERT ... ON CONFLICT DO NOTHING closes the race where two
        concurrent first-ever movements for the same (product, warehouse) both
        try to create the row. After it, SELECT ... FOR UPDATE serialises every
        reader, which is what stops two sales from spending the same unit
        (BACKEND.md section 29).
        """
        upsert = (
            pg_insert(ProductStockModel)
            .values(
                company_id=company_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=Decimal("0"),
            )
            .on_conflict_do_nothing(
                index_elements=["company_id", "product_id", "warehouse_id"],
            )
        )
        await self._session.execute(upsert)

        stmt = (
            select(ProductStockModel)
            .where(
                ProductStockModel.company_id == company_id,
                ProductStockModel.product_id == product_id,
                ProductStockModel.warehouse_id == warehouse_id,
            )
            .with_for_update()
        )
        model = (await self._session.execute(stmt)).scalar_one()
        return product_stock_to_domain(model)

    async def get(
        self, company_id: uuid.UUID, product_id: uuid.UUID, warehouse_id: uuid.UUID
    ) -> ProductStock | None:
        stmt = select(ProductStockModel).where(
            ProductStockModel.company_id == company_id,
            ProductStockModel.product_id == product_id,
            ProductStockModel.warehouse_id == warehouse_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return product_stock_to_domain(model) if model else None

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        only_non_zero: bool = False,
    ) -> PaginatedResult[ProductStock]:
        filters = [ProductStockModel.company_id == company_id]
        if product_id is not None:
            filters.append(ProductStockModel.product_id == product_id)
        if warehouse_id is not None:
            filters.append(ProductStockModel.warehouse_id == warehouse_id)
        if only_non_zero:
            filters.append(ProductStockModel.quantity != 0)

        total = (
            await self._session.execute(
                select(func.count()).select_from(ProductStockModel).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(ProductStockModel)
            .where(*filters)
            .order_by(ProductStockModel.updated_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[product_stock_to_domain(row) for row in rows], total=total, page=page
        )

    async def save(self, stock: ProductStock) -> ProductStock:
        stmt = select(ProductStockModel).where(
            ProductStockModel.id == stock.id,
            ProductStockModel.company_id == stock.company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Stock row {stock.id} disappeared before update")
        model.quantity = stock.quantity
        await self._session.flush()
        return product_stock_to_domain(model)


class SqlAlchemyStockMovementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, movement: StockMovement) -> StockMovement:
        model = StockMovementModel(
            id=movement.id,
            company_id=movement.company_id,
            product_id=movement.product_id,
            warehouse_id=movement.warehouse_id,
            movement_type=movement.movement_type,
            quantity=movement.quantity,
            reference_type=movement.reference_type,
            reference_id=movement.reference_id,
            notes=movement.notes,
            created_by=movement.created_by,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return stock_movement_to_domain(model)

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        product_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
        reference_id: uuid.UUID | None = None,
    ) -> PaginatedResult[StockMovement]:
        filters = [StockMovementModel.company_id == company_id]
        if product_id is not None:
            filters.append(StockMovementModel.product_id == product_id)
        if warehouse_id is not None:
            filters.append(StockMovementModel.warehouse_id == warehouse_id)
        if reference_id is not None:
            filters.append(StockMovementModel.reference_id == reference_id)

        total = (
            await self._session.execute(
                select(func.count()).select_from(StockMovementModel).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(StockMovementModel)
            .where(*filters)
            .order_by(StockMovementModel.created_at.desc(), StockMovementModel.id.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[stock_movement_to_domain(row) for row in rows], total=total, page=page
        )
