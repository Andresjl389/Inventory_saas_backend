import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.application.purchases.dto.purchase import (
    CreatePurchaseCommand,
    ListPurchasesQuery,
    PurchaseDTO,
    PurchasePageDTO,
)
from app.application.purchases.use_cases.purchase_use_cases import (
    CancelPurchaseUseCase,
    CompletePurchaseUseCase,
    CreatePurchaseUseCase,
    GetPurchaseUseCase,
    ListPurchasesUseCase,
)
from app.domain.purchases.entities.purchase import PurchaseStatus
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import (
    ProductRepoDep,
    PurchaseRepoDep,
    StockServiceDep,
    SupplierRepoDep,
    WarehouseRepoDep,
)
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/purchases", tags=["purchases"])

ReadDep = Annotated[TenantContext, Depends(require_permission("purchases.read"))]
CreateDep = Annotated[TenantContext, Depends(require_permission("purchases.create"))]
CancelDep = Annotated[TenantContext, Depends(require_permission("purchases.cancel"))]


@router.get("", response_model=PurchasePageDTO)
async def list_purchases(
    tenant: ReadDep,
    purchases: PurchaseRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    purchase_status: Annotated[PurchaseStatus | None, Query(alias="status")] = None,
    supplier_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> PurchasePageDTO:
    query = ListPurchasesQuery(
        page=page,
        size=size,
        status=purchase_status,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
    )
    return await ListPurchasesUseCase(purchases).execute(query, tenant=tenant)


@router.post("", response_model=PurchaseDTO, status_code=status.HTTP_201_CREATED)
async def create_purchase(
    command: CreatePurchaseCommand,
    tenant: CreateDep,
    purchases: PurchaseRepoDep,
    products: ProductRepoDep,
    warehouses: WarehouseRepoDep,
    suppliers: SupplierRepoDep,
    stock_service: StockServiceDep,
) -> PurchaseDTO:
    use_case = CreatePurchaseUseCase(purchases, products, warehouses, suppliers, stock_service)
    return await use_case.execute(command, tenant=tenant)


@router.get("/{purchase_id}", response_model=PurchaseDTO)
async def get_purchase(
    purchase_id: uuid.UUID, tenant: ReadDep, purchases: PurchaseRepoDep
) -> PurchaseDTO:
    return await GetPurchaseUseCase(purchases).execute(purchase_id, tenant=tenant)


@router.post("/{purchase_id}/complete", response_model=PurchaseDTO)
async def complete_purchase(
    purchase_id: uuid.UUID,
    tenant: CreateDep,
    purchases: PurchaseRepoDep,
    products: ProductRepoDep,
    stock_service: StockServiceDep,
    update_product_costs: Annotated[bool, Query()] = False,
) -> PurchaseDTO:
    """Receive the goods. `update_product_costs=true` also refreshes each
    product's cost_price with what was actually paid."""
    use_case = CompletePurchaseUseCase(purchases, products, stock_service)
    return await use_case.execute(
        purchase_id, tenant=tenant, update_product_costs=update_product_costs
    )


@router.post("/{purchase_id}/cancel", response_model=PurchaseDTO)
async def cancel_purchase(
    purchase_id: uuid.UUID,
    tenant: CancelDep,
    purchases: PurchaseRepoDep,
    stock_service: StockServiceDep,
) -> PurchaseDTO:
    return await CancelPurchaseUseCase(purchases, stock_service).execute(purchase_id, tenant=tenant)
