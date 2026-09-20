from app.application.inventory.dto.stock import (
    AdjustStockCommand,
    ListMovementsQuery,
    ListStockQuery,
    MovementPageDTO,
    ProductStockDTO,
    StockMovementDTO,
    StockPageDTO,
    TransferResultDTO,
    TransferStockCommand,
)
from app.application.inventory.services.stock_service import StockService
from app.domain.inventory.entities.stock_movement import MovementType, ReferenceType
from app.domain.inventory.exceptions import (
    InactiveWarehouseError,
    InvalidMovementError,
    SameWarehouseTransferError,
    WarehouseNotFoundError,
)
from app.domain.inventory.repositories.stock_repository import (
    StockMovementRepository,
    StockRepository,
)
from app.domain.inventory.repositories.warehouse_repository import WarehouseRepository
from app.domain.products.exceptions import ProductNotFoundError
from app.domain.products.repositories.product_repository import ProductRepository
from app.domain.shared.pagination import Page
from app.domain.tenants.tenant_context import TenantContext


class GetStockUseCase:
    def __init__(self, stock: StockRepository) -> None:
        self._stock = stock

    async def execute(self, query: ListStockQuery, *, tenant: TenantContext) -> StockPageDTO:
        result = await self._stock.list(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            product_id=query.product_id,
            warehouse_id=query.warehouse_id,
            only_non_zero=query.only_non_zero,
        )
        return StockPageDTO(
            items=[
                ProductStockDTO.model_validate(row, from_attributes=True) for row in result.items
            ],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class GetStockMovementsUseCase:
    def __init__(self, movements: StockMovementRepository) -> None:
        self._movements = movements

    async def execute(self, query: ListMovementsQuery, *, tenant: TenantContext) -> MovementPageDTO:
        result = await self._movements.list(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            product_id=query.product_id,
            warehouse_id=query.warehouse_id,
            reference_id=query.reference_id,
        )
        return MovementPageDTO(
            items=[
                StockMovementDTO.model_validate(row, from_attributes=True) for row in result.items
            ],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class _StockOperation:
    """Shared validation for the operations that move stock by hand."""

    def __init__(
        self,
        stock_service: StockService,
        products: ProductRepository,
        warehouses: WarehouseRepository,
    ) -> None:
        self._stock_service = stock_service
        self._products = products
        self._warehouses = warehouses

    async def _assert_product(self, tenant: TenantContext, product_id) -> None:
        if await self._products.get_by_id(tenant.company_id, product_id) is None:
            raise ProductNotFoundError()

    async def _assert_active_warehouse(self, tenant: TenantContext, warehouse_id) -> None:
        warehouse = await self._warehouses.get_by_id(tenant.company_id, warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError()
        if not warehouse.is_active:
            raise InactiveWarehouseError(f"Warehouse '{warehouse.name}' is not active")


class AdjustStockUseCase(_StockOperation):
    """Manual correction: stocktake differences, breakage, shrinkage."""

    async def execute(
        self, command: AdjustStockCommand, *, tenant: TenantContext
    ) -> ProductStockDTO:
        if command.quantity_delta == 0:
            raise InvalidMovementError("An adjustment of zero changes nothing")

        await self._assert_product(tenant, command.product_id)
        await self._assert_active_warehouse(tenant, command.warehouse_id)

        stock = await self._stock_service.apply_movement(
            company_id=tenant.company_id,
            product_id=command.product_id,
            warehouse_id=command.warehouse_id,
            delta=command.quantity_delta,
            movement_type=MovementType.ADJUSTMENT,
            reference_type=ReferenceType.MANUAL,
            notes=command.notes,
            created_by=tenant.user_id,
        )
        return ProductStockDTO.model_validate(stock, from_attributes=True)


class TransferStockUseCase(_StockOperation):
    """Move stock between two warehouses of the same company.

    Both legs happen in the caller's transaction, so stock is never in flight:
    either both movements land or neither does.
    """

    async def execute(
        self, command: TransferStockCommand, *, tenant: TenantContext
    ) -> TransferResultDTO:
        if command.source_warehouse_id == command.destination_warehouse_id:
            raise SameWarehouseTransferError()

        await self._assert_product(tenant, command.product_id)
        await self._assert_active_warehouse(tenant, command.source_warehouse_id)
        await self._assert_active_warehouse(tenant, command.destination_warehouse_id)

        # Lock in a fixed order (source before destination is not enough --
        # two opposite transfers would deadlock), so order by warehouse id.
        first, second = sorted([command.source_warehouse_id, command.destination_warehouse_id])
        legs = {
            command.source_warehouse_id: (-command.quantity, MovementType.TRANSFER_OUT),
            command.destination_warehouse_id: (command.quantity, MovementType.TRANSFER_IN),
        }

        results = {}
        for warehouse_id in (first, second):
            delta, movement_type = legs[warehouse_id]
            results[warehouse_id] = await self._stock_service.apply_movement(
                company_id=tenant.company_id,
                product_id=command.product_id,
                warehouse_id=warehouse_id,
                delta=delta,
                movement_type=movement_type,
                reference_type=ReferenceType.TRANSFER,
                notes=command.notes,
                created_by=tenant.user_id,
            )

        return TransferResultDTO(
            source=ProductStockDTO.model_validate(
                results[command.source_warehouse_id], from_attributes=True
            ),
            destination=ProductStockDTO.model_validate(
                results[command.destination_warehouse_id], from_attributes=True
            ),
        )
