import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.inventory.entities.warehouse import Warehouse
from app.infrastructure.database.models.inventory import WarehouseModel
from app.infrastructure.database.repositories.mappers import warehouse_to_domain


class SqlAlchemyWarehouseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse | None:
        stmt = select(WarehouseModel).where(
            WarehouseModel.id == warehouse_id,
            WarehouseModel.company_id == company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return warehouse_to_domain(model) if model else None

    async def get_by_name(self, company_id: uuid.UUID, name: str) -> Warehouse | None:
        stmt = select(WarehouseModel).where(
            WarehouseModel.company_id == company_id,
            WarehouseModel.name == name,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return warehouse_to_domain(model) if model else None

    async def list(
        self, company_id: uuid.UUID, *, is_active: bool | None = None
    ) -> list[Warehouse]:
        filters = [WarehouseModel.company_id == company_id]
        if is_active is not None:
            filters.append(WarehouseModel.is_active.is_(is_active))
        stmt = select(WarehouseModel).where(*filters).order_by(WarehouseModel.name)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [warehouse_to_domain(row) for row in rows]

    async def add(self, warehouse: Warehouse) -> Warehouse:
        model = WarehouseModel(
            id=warehouse.id,
            company_id=warehouse.company_id,
            name=warehouse.name,
            address=warehouse.address,
            is_active=warehouse.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return warehouse_to_domain(model)

    async def update(self, warehouse: Warehouse) -> Warehouse:
        stmt = select(WarehouseModel).where(
            WarehouseModel.id == warehouse.id,
            WarehouseModel.company_id == warehouse.company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Warehouse {warehouse.id} disappeared before update")
        model.name = warehouse.name
        model.address = warehouse.address
        model.is_active = warehouse.is_active
        await self._session.flush()
        return warehouse_to_domain(model)
