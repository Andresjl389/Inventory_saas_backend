import uuid

from app.application.inventory.dto.warehouse import (
    CreateWarehouseCommand,
    UpdateWarehouseCommand,
    WarehouseDTO,
)
from app.domain.inventory.entities.warehouse import Warehouse
from app.domain.inventory.exceptions import (
    DuplicateWarehouseNameError,
    WarehouseNotFoundError,
)
from app.domain.inventory.repositories.warehouse_repository import WarehouseRepository
from app.domain.tenants.tenant_context import TenantContext


class CreateWarehouseUseCase:
    def __init__(self, warehouses: WarehouseRepository) -> None:
        self._warehouses = warehouses

    async def execute(
        self, command: CreateWarehouseCommand, *, tenant: TenantContext
    ) -> WarehouseDTO:
        name = command.name.strip()
        if await self._warehouses.get_by_name(tenant.company_id, name) is not None:
            raise DuplicateWarehouseNameError()

        warehouse = await self._warehouses.add(
            Warehouse(company_id=tenant.company_id, name=name, address=command.address)
        )
        return WarehouseDTO.model_validate(warehouse, from_attributes=True)


class ListWarehousesUseCase:
    def __init__(self, warehouses: WarehouseRepository) -> None:
        self._warehouses = warehouses

    async def execute(
        self, *, tenant: TenantContext, is_active: bool | None = None
    ) -> list[WarehouseDTO]:
        rows = await self._warehouses.list(tenant.company_id, is_active=is_active)
        return [WarehouseDTO.model_validate(row, from_attributes=True) for row in rows]


class GetWarehouseUseCase:
    def __init__(self, warehouses: WarehouseRepository) -> None:
        self._warehouses = warehouses

    async def execute(self, warehouse_id: uuid.UUID, *, tenant: TenantContext) -> WarehouseDTO:
        warehouse = await self._warehouses.get_by_id(tenant.company_id, warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError()
        return WarehouseDTO.model_validate(warehouse, from_attributes=True)


class UpdateWarehouseUseCase:
    def __init__(self, warehouses: WarehouseRepository) -> None:
        self._warehouses = warehouses

    async def execute(
        self,
        warehouse_id: uuid.UUID,
        command: UpdateWarehouseCommand,
        *,
        tenant: TenantContext,
    ) -> WarehouseDTO:
        warehouse = await self._warehouses.get_by_id(tenant.company_id, warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError()

        if command.name is not None:
            name = command.name.strip()
            clash = await self._warehouses.get_by_name(tenant.company_id, name)
            if clash is not None and clash.id != warehouse.id:
                raise DuplicateWarehouseNameError()
            warehouse.rename(name)

        if command.address is not None:
            warehouse.address = command.address
            warehouse.touch()

        if command.is_active is not None:
            warehouse.activate() if command.is_active else warehouse.deactivate()

        updated = await self._warehouses.update(warehouse)
        return WarehouseDTO.model_validate(updated, from_attributes=True)


class DeactivateWarehouseUseCase:
    """Warehouses are never deleted: stock movements reference them forever."""

    def __init__(self, warehouses: WarehouseRepository) -> None:
        self._warehouses = warehouses

    async def execute(self, warehouse_id: uuid.UUID, *, tenant: TenantContext) -> WarehouseDTO:
        warehouse = await self._warehouses.get_by_id(tenant.company_id, warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError()
        warehouse.deactivate()
        updated = await self._warehouses.update(warehouse)
        return WarehouseDTO.model_validate(updated, from_attributes=True)
