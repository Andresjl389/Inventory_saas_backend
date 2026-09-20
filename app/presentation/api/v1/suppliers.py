import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.application.suppliers.dto.supplier import (
    CreateSupplierCommand,
    ListSuppliersQuery,
    SupplierDTO,
    SupplierPageDTO,
    UpdateSupplierCommand,
)
from app.application.suppliers.use_cases.supplier_use_cases import (
    CreateSupplierUseCase,
    DeactivateSupplierUseCase,
    GetSupplierUseCase,
    ListSuppliersUseCase,
    UpdateSupplierUseCase,
)
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import SupplierRepoDep
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

ReadDep = Annotated[TenantContext, Depends(require_permission("suppliers.read"))]
WriteDep = Annotated[TenantContext, Depends(require_permission("suppliers.write"))]


@router.get("", response_model=SupplierPageDTO)
async def list_suppliers(
    tenant: ReadDep,
    suppliers: SupplierRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
) -> SupplierPageDTO:
    query = ListSuppliersQuery(page=page, size=size, search=search, is_active=is_active)
    return await ListSuppliersUseCase(suppliers).execute(query, tenant=tenant)


@router.post("", response_model=SupplierDTO, status_code=status.HTTP_201_CREATED)
async def create_supplier(
    command: CreateSupplierCommand, tenant: WriteDep, suppliers: SupplierRepoDep
) -> SupplierDTO:
    return await CreateSupplierUseCase(suppliers).execute(command, tenant=tenant)


@router.get("/{supplier_id}", response_model=SupplierDTO)
async def get_supplier(
    supplier_id: uuid.UUID, tenant: ReadDep, suppliers: SupplierRepoDep
) -> SupplierDTO:
    return await GetSupplierUseCase(suppliers).execute(supplier_id, tenant=tenant)


@router.patch("/{supplier_id}", response_model=SupplierDTO)
async def update_supplier(
    supplier_id: uuid.UUID,
    command: UpdateSupplierCommand,
    tenant: WriteDep,
    suppliers: SupplierRepoDep,
) -> SupplierDTO:
    return await UpdateSupplierUseCase(suppliers).execute(supplier_id, command, tenant=tenant)


@router.delete("/{supplier_id}", response_model=SupplierDTO)
async def deactivate_supplier(
    supplier_id: uuid.UUID, tenant: WriteDep, suppliers: SupplierRepoDep
) -> SupplierDTO:
    return await DeactivateSupplierUseCase(suppliers).execute(supplier_id, tenant=tenant)
