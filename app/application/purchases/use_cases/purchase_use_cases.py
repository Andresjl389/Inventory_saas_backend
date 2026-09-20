"""Purchase use cases: the mirror of sales, adding stock instead of removing it."""

import uuid

from app.application.inventory.services.stock_service import StockService
from app.application.purchases.dto.purchase import (
    CreatePurchaseCommand,
    ListPurchasesQuery,
    PurchaseDTO,
    PurchasePageDTO,
)
from app.domain.inventory.entities.stock_movement import MovementType, ReferenceType
from app.domain.inventory.exceptions import InactiveWarehouseError, WarehouseNotFoundError
from app.domain.inventory.repositories.warehouse_repository import WarehouseRepository
from app.domain.products.exceptions import ProductNotFoundError
from app.domain.products.repositories.product_repository import ProductRepository
from app.domain.purchases.entities.purchase import Purchase, PurchaseItem
from app.domain.purchases.exceptions import PurchaseNotFoundError
from app.domain.purchases.repositories.purchase_repository import PurchaseRepository
from app.domain.shared.pagination import Page
from app.domain.suppliers.exceptions import InactiveSupplierError, SupplierNotFoundError
from app.domain.suppliers.repositories.supplier_repository import SupplierRepository
from app.domain.tenants.tenant_context import TenantContext


class _PurchaseStockMixin:
    _stock_service: StockService

    async def _move_stock(
        self,
        purchase: Purchase,
        *,
        incoming: bool,
        tenant: TenantContext,
        notes: str | None = None,
    ) -> None:
        for item in sorted(purchase.items, key=lambda i: str(i.product_id)):
            delta = item.quantity if incoming else -item.quantity
            await self._stock_service.apply_movement(
                company_id=tenant.company_id,
                product_id=item.product_id,
                warehouse_id=purchase.warehouse_id,
                delta=delta,
                # Reversing a purchase is modelled as an ADJUSTMENT, not a
                # negative PURCHASE: purchase volume reports must not net out.
                movement_type=(MovementType.PURCHASE if incoming else MovementType.ADJUSTMENT),
                reference_type=ReferenceType.PURCHASE,
                reference_id=purchase.id,
                notes=notes,
                created_by=tenant.user_id,
            )


class CreatePurchaseUseCase(_PurchaseStockMixin):
    def __init__(
        self,
        purchases: PurchaseRepository,
        products: ProductRepository,
        warehouses: WarehouseRepository,
        suppliers: SupplierRepository,
        stock_service: StockService,
    ) -> None:
        self._purchases = purchases
        self._products = products
        self._warehouses = warehouses
        self._suppliers = suppliers
        self._stock_service = stock_service

    async def execute(
        self, command: CreatePurchaseCommand, *, tenant: TenantContext
    ) -> PurchaseDTO:
        warehouse = await self._warehouses.get_by_id(tenant.company_id, command.warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError()
        if not warehouse.is_active:
            raise InactiveWarehouseError(f"Warehouse '{warehouse.name}' is not active")

        if command.supplier_id is not None:
            supplier = await self._suppliers.get_by_id(tenant.company_id, command.supplier_id)
            if supplier is None:
                raise SupplierNotFoundError()
            if not supplier.is_active:
                raise InactiveSupplierError(f"Supplier '{supplier.name}' is not active")

        purchase_id = uuid.uuid4()
        items: list[PurchaseItem] = []
        for line in command.items:
            product = await self._products.get_by_id(tenant.company_id, line.product_id)
            if product is None:
                raise ProductNotFoundError(
                    "Product not found", details={"product_id": str(line.product_id)}
                )
            items.append(
                PurchaseItem(
                    company_id=tenant.company_id,
                    purchase_id=purchase_id,
                    product_id=product.id,
                    quantity=line.quantity,
                    unit_cost=line.unit_cost,
                    discount=line.discount,
                    tax=line.tax,
                )
            )

        purchase = Purchase(
            id=purchase_id,
            company_id=tenant.company_id,
            supplier_id=command.supplier_id,
            warehouse_id=command.warehouse_id,
            notes=command.notes,
            created_by=tenant.user_id,
            items=items,
        )

        if command.complete:
            purchase.complete()

        created = await self._purchases.add(purchase)

        if command.complete:
            await self._move_stock(created, incoming=True, tenant=tenant)
            if command.update_product_costs:
                await self._refresh_costs(created, tenant=tenant)

        return PurchaseDTO.model_validate(created, from_attributes=True)

    async def _refresh_costs(self, purchase: Purchase, *, tenant: TenantContext) -> None:
        for item in purchase.items:
            product = await self._products.get_by_id(tenant.company_id, item.product_id)
            if product is None:
                continue
            product.update_prices(cost_price=item.net_unit_cost, sale_price=None)
            await self._products.update(product)


class GetPurchaseUseCase:
    def __init__(self, purchases: PurchaseRepository) -> None:
        self._purchases = purchases

    async def execute(self, purchase_id: uuid.UUID, *, tenant: TenantContext) -> PurchaseDTO:
        purchase = await self._purchases.get_by_id(tenant.company_id, purchase_id)
        if purchase is None:
            raise PurchaseNotFoundError()
        return PurchaseDTO.model_validate(purchase, from_attributes=True)


class ListPurchasesUseCase:
    def __init__(self, purchases: PurchaseRepository) -> None:
        self._purchases = purchases

    async def execute(self, query: ListPurchasesQuery, *, tenant: TenantContext) -> PurchasePageDTO:
        result = await self._purchases.list(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            status=query.status,
            supplier_id=query.supplier_id,
            warehouse_id=query.warehouse_id,
        )
        return PurchasePageDTO(
            items=[PurchaseDTO.model_validate(row, from_attributes=True) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class CompletePurchaseUseCase(_PurchaseStockMixin):
    def __init__(
        self,
        purchases: PurchaseRepository,
        products: ProductRepository,
        stock_service: StockService,
    ) -> None:
        self._purchases = purchases
        self._products = products
        self._stock_service = stock_service

    async def execute(
        self,
        purchase_id: uuid.UUID,
        *,
        tenant: TenantContext,
        update_product_costs: bool = False,
    ) -> PurchaseDTO:
        purchase = await self._purchases.get_by_id(tenant.company_id, purchase_id)
        if purchase is None:
            raise PurchaseNotFoundError()

        purchase.complete()
        await self._move_stock(purchase, incoming=True, tenant=tenant)

        if update_product_costs:
            for item in purchase.items:
                product = await self._products.get_by_id(tenant.company_id, item.product_id)
                if product is None:
                    continue
                product.update_prices(cost_price=item.net_unit_cost, sale_price=None)
                await self._products.update(product)

        updated = await self._purchases.update_header(purchase)
        return PurchaseDTO.model_validate(updated, from_attributes=True)


class CancelPurchaseUseCase(_PurchaseStockMixin):
    """Cancelling a received purchase takes the goods back out of stock, which
    can only happen if they are still there."""

    def __init__(self, purchases: PurchaseRepository, stock_service: StockService) -> None:
        self._purchases = purchases
        self._stock_service = stock_service

    async def execute(self, purchase_id: uuid.UUID, *, tenant: TenantContext) -> PurchaseDTO:
        purchase = await self._purchases.get_by_id(tenant.company_id, purchase_id)
        if purchase is None:
            raise PurchaseNotFoundError()

        reverse = purchase.affects_stock
        purchase.cancel()
        if reverse:
            await self._move_stock(
                purchase, incoming=False, tenant=tenant, notes="Purchase cancelled"
            )
        updated = await self._purchases.update_header(purchase)
        return PurchaseDTO.model_validate(updated, from_attributes=True)
