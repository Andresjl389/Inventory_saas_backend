import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.application.customers.dto.customer import (
    CreateCustomerCommand,
    CustomerDTO,
    CustomerPageDTO,
    ListCustomersQuery,
    UpdateCustomerCommand,
)
from app.application.customers.use_cases.customer_use_cases import (
    CreateCustomerUseCase,
    DeactivateCustomerUseCase,
    GetCustomerUseCase,
    ListCustomersUseCase,
    UpdateCustomerUseCase,
)
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import CustomerRepoDep
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/customers", tags=["customers"])

ReadDep = Annotated[TenantContext, Depends(require_permission("customers.read"))]
WriteDep = Annotated[TenantContext, Depends(require_permission("customers.write"))]


@router.get("", response_model=CustomerPageDTO)
async def list_customers(
    tenant: ReadDep,
    customers: CustomerRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
) -> CustomerPageDTO:
    query = ListCustomersQuery(page=page, size=size, search=search, is_active=is_active)
    return await ListCustomersUseCase(customers).execute(query, tenant=tenant)


@router.post("", response_model=CustomerDTO, status_code=status.HTTP_201_CREATED)
async def create_customer(
    command: CreateCustomerCommand, tenant: WriteDep, customers: CustomerRepoDep
) -> CustomerDTO:
    return await CreateCustomerUseCase(customers).execute(command, tenant=tenant)


@router.get("/{customer_id}", response_model=CustomerDTO)
async def get_customer(
    customer_id: uuid.UUID, tenant: ReadDep, customers: CustomerRepoDep
) -> CustomerDTO:
    return await GetCustomerUseCase(customers).execute(customer_id, tenant=tenant)


@router.patch("/{customer_id}", response_model=CustomerDTO)
async def update_customer(
    customer_id: uuid.UUID,
    command: UpdateCustomerCommand,
    tenant: WriteDep,
    customers: CustomerRepoDep,
) -> CustomerDTO:
    return await UpdateCustomerUseCase(customers).execute(customer_id, command, tenant=tenant)


@router.delete("/{customer_id}", response_model=CustomerDTO)
async def deactivate_customer(
    customer_id: uuid.UUID, tenant: WriteDep, customers: CustomerRepoDep
) -> CustomerDTO:
    return await DeactivateCustomerUseCase(customers).execute(customer_id, tenant=tenant)
