import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.application.sales.dto.sale import (
    CreateSaleCommand,
    ListSalesQuery,
    SaleDTO,
    SalePageDTO,
)
from app.application.sales.use_cases.sale_use_cases import (
    CancelSaleUseCase,
    CompleteSaleUseCase,
    CreateSaleUseCase,
    GetSaleUseCase,
    ListSalesUseCase,
    RefundSaleUseCase,
)
from app.domain.sales.entities.sale import SaleStatus
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import (
    CustomerRepoDep,
    ProductRepoDep,
    SaleRepoDep,
    StockServiceDep,
    WarehouseRepoDep,
)
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/sales", tags=["sales"])

ReadDep = Annotated[TenantContext, Depends(require_permission("sales.read"))]
CreateDep = Annotated[TenantContext, Depends(require_permission("sales.create"))]
CancelDep = Annotated[TenantContext, Depends(require_permission("sales.cancel"))]


@router.get("", response_model=SalePageDTO)
async def list_sales(
    tenant: ReadDep,
    sales: SaleRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    sale_status: Annotated[SaleStatus | None, Query(alias="status")] = None,
    customer_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> SalePageDTO:
    query = ListSalesQuery(
        page=page,
        size=size,
        status=sale_status,
        customer_id=customer_id,
        warehouse_id=warehouse_id,
    )
    return await ListSalesUseCase(sales).execute(query, tenant=tenant)


@router.post("", response_model=SaleDTO, status_code=status.HTTP_201_CREATED)
async def create_sale(
    command: CreateSaleCommand,
    tenant: CreateDep,
    sales: SaleRepoDep,
    products: ProductRepoDep,
    warehouses: WarehouseRepoDep,
    customers: CustomerRepoDep,
    stock_service: StockServiceDep,
) -> SaleDTO:
    """Create a sale. With `complete: true` the stock moves in the same
    transaction -- nothing is half-done if a line runs out of stock."""
    use_case = CreateSaleUseCase(sales, products, warehouses, customers, stock_service)
    return await use_case.execute(command, tenant=tenant)


@router.get("/{sale_id}", response_model=SaleDTO)
async def get_sale(sale_id: uuid.UUID, tenant: ReadDep, sales: SaleRepoDep) -> SaleDTO:
    return await GetSaleUseCase(sales).execute(sale_id, tenant=tenant)


@router.post("/{sale_id}/complete", response_model=SaleDTO)
async def complete_sale(
    sale_id: uuid.UUID, tenant: CreateDep, sales: SaleRepoDep, stock_service: StockServiceDep
) -> SaleDTO:
    return await CompleteSaleUseCase(sales, stock_service).execute(sale_id, tenant=tenant)


@router.post("/{sale_id}/cancel", response_model=SaleDTO)
async def cancel_sale(
    sale_id: uuid.UUID, tenant: CancelDep, sales: SaleRepoDep, stock_service: StockServiceDep
) -> SaleDTO:
    return await CancelSaleUseCase(sales, stock_service).execute(sale_id, tenant=tenant)


@router.post("/{sale_id}/refund", response_model=SaleDTO)
async def refund_sale(
    sale_id: uuid.UUID, tenant: CancelDep, sales: SaleRepoDep, stock_service: StockServiceDep
) -> SaleDTO:
    return await RefundSaleUseCase(sales, stock_service).execute(sale_id, tenant=tenant)
