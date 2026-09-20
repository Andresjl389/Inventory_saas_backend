import uuid
from typing import Protocol

from app.domain.inventory.entities.warehouse import Warehouse


class WarehouseRepository(Protocol):
    async def get_by_id(
        self, company_id: uuid.UUID, warehouse_id: uuid.UUID
    ) -> Warehouse | None: ...

    async def get_by_name(self, company_id: uuid.UUID, name: str) -> Warehouse | None: ...

    async def list(
        self, company_id: uuid.UUID, *, is_active: bool | None = None
    ) -> list[Warehouse]: ...

    async def add(self, warehouse: Warehouse) -> Warehouse: ...

    async def update(self, warehouse: Warehouse) -> Warehouse: ...
