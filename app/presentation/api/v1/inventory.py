import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.inventory.dto.stock import (
    AdjustStockCommand,
    ListMovementsQuery,
    ListStockQuery,
    MovementPageDTO,
    ProductStockDTO,
    StockPageDTO,
    TransferResultDTO,
    TransferStockCommand,
)
from app.application.inventory.use_cases.stock_use_cases import (
    AdjustStockUseCase,
    GetStockMovementsUseCase,
    GetStockUseCase,
    TransferStockUseCase,
)
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import (
    MovementRepoDep,
    ProductRepoDep,
    StockRepoDep,
    StockServiceDep,
    WarehouseRepoDep,
)
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/inventory", tags=["inventory"])

ReadDep = Annotated[TenantContext, Depends(require_permission("inventory.read"))]
AdjustDep = Annotated[TenantContext, Depends(require_permission("inventory.adjust"))]
TransferDep = Annotated[TenantContext, Depends(require_permission("inventory.transfer"))]


@router.get("/stock", response_model=StockPageDTO)
async def get_stock(
    tenant: ReadDep,
    stock: StockRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    only_non_zero: bool = False,
) -> StockPageDTO:
    query = ListStockQuery(
        page=page,
        size=size,
        product_id=product_id,
        warehouse_id=warehouse_id,
        only_non_zero=only_non_zero,
    )
    return await GetStockUseCase(stock).execute(query, tenant=tenant)


@router.get("/movements", response_model=MovementPageDTO)
async def get_movements(
    tenant: ReadDep,
    movements: MovementRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    reference_id: uuid.UUID | None = None,
) -> MovementPageDTO:
    """The audit trail: every change to stock, newest first."""
    query = ListMovementsQuery(
        page=page,
        size=size,
        product_id=product_id,
        warehouse_id=warehouse_id,
        reference_id=reference_id,
    )
    return await GetStockMovementsUseCase(movements).execute(query, tenant=tenant)


@router.post("/adjustments", response_model=ProductStockDTO)
async def adjust_stock(
    command: AdjustStockCommand,
    tenant: AdjustDep,
    stock_service: StockServiceDep,
    products: ProductRepoDep,
    warehouses: WarehouseRepoDep,
) -> ProductStockDTO:
    use_case = AdjustStockUseCase(stock_service, products, warehouses)
    return await use_case.execute(command, tenant=tenant)


@router.post("/transfers", response_model=TransferResultDTO)
async def transfer_stock(
    command: TransferStockCommand,
    tenant: TransferDep,
    stock_service: StockServiceDep,
    products: ProductRepoDep,
    warehouses: WarehouseRepoDep,
) -> TransferResultDTO:
    use_case = TransferStockUseCase(stock_service, products, warehouses)
    return await use_case.execute(command, tenant=tenant)
