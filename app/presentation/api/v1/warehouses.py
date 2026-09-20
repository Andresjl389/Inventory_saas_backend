import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.application.inventory.dto.warehouse import (
    CreateWarehouseCommand,
    UpdateWarehouseCommand,
    WarehouseDTO,
)
from app.application.inventory.use_cases.warehouse_use_cases import (
    CreateWarehouseUseCase,
    DeactivateWarehouseUseCase,
    GetWarehouseUseCase,
    ListWarehousesUseCase,
    UpdateWarehouseUseCase,
)
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import WarehouseRepoDep
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/warehouses", tags=["warehouses"])

ReadDep = Annotated[TenantContext, Depends(require_permission("warehouses.read"))]
WriteDep = Annotated[TenantContext, Depends(require_permission("warehouses.write"))]


@router.get("", response_model=list[WarehouseDTO])
async def list_warehouses(
    tenant: ReadDep,
    warehouses: WarehouseRepoDep,
    is_active: Annotated[bool | None, Query()] = None,
) -> list[WarehouseDTO]:
    return await ListWarehousesUseCase(warehouses).execute(tenant=tenant, is_active=is_active)


@router.post("", response_model=WarehouseDTO, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    command: CreateWarehouseCommand, tenant: WriteDep, warehouses: WarehouseRepoDep
) -> WarehouseDTO:
    return await CreateWarehouseUseCase(warehouses).execute(command, tenant=tenant)


@router.get("/{warehouse_id}", response_model=WarehouseDTO)
async def get_warehouse(
    warehouse_id: uuid.UUID, tenant: ReadDep, warehouses: WarehouseRepoDep
) -> WarehouseDTO:
    return await GetWarehouseUseCase(warehouses).execute(warehouse_id, tenant=tenant)


@router.patch("/{warehouse_id}", response_model=WarehouseDTO)
async def update_warehouse(
    warehouse_id: uuid.UUID,
    command: UpdateWarehouseCommand,
    tenant: WriteDep,
    warehouses: WarehouseRepoDep,
) -> WarehouseDTO:
    return await UpdateWarehouseUseCase(warehouses).execute(warehouse_id, command, tenant=tenant)


@router.delete("/{warehouse_id}", response_model=WarehouseDTO)
async def deactivate_warehouse(
    warehouse_id: uuid.UUID, tenant: WriteDep, warehouses: WarehouseRepoDep
) -> WarehouseDTO:
    """Soft delete: stock movements reference warehouses permanently."""
    return await DeactivateWarehouseUseCase(warehouses).execute(warehouse_id, tenant=tenant)
