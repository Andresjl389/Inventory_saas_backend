"""Sales use cases.

Completing a sale is the transaction sketched in BACKEND.md section 28: lock
stock, check availability, write the movements, update the cached quantities.
Every step runs inside the request transaction, so any failure rolls the whole
sale back -- there is no state where stock left the warehouse but the sale did
not record it.
"""

import uuid

from app.application.inventory.services.stock_service import StockService
from app.application.sales.dto.sale import (
    CreateSaleCommand,
    ListSalesQuery,
    SaleDTO,
    SalePageDTO,
)
from app.domain.customers.exceptions import CustomerNotFoundError, InactiveCustomerError
from app.domain.customers.repositories.customer_repository import CustomerRepository
from app.domain.inventory.entities.stock_movement import MovementType, ReferenceType
from app.domain.inventory.exceptions import InactiveWarehouseError, WarehouseNotFoundError
from app.domain.inventory.repositories.warehouse_repository import WarehouseRepository
from app.domain.products.exceptions import ProductNotFoundError
from app.domain.products.repositories.product_repository import ProductRepository
from app.domain.sales.entities.sale import Sale, SaleItem
from app.domain.sales.exceptions import SaleNotFoundError
from app.domain.sales.repositories.sale_repository import SaleRepository
from app.domain.shared.pagination import Page
from app.domain.tenants.tenant_context import TenantContext
from app.shared.exceptions import BusinessRuleError


class _SaleStockMixin:
    _stock_service: StockService

    async def _move_stock(
        self, sale: Sale, *, outgoing: bool, tenant: TenantContext, notes: str | None = None
    ) -> None:
        """Apply (or reverse) the stock effect of every line.

        Lines are processed in product order so concurrent sales always take
        row locks in the same sequence and cannot deadlock against each other.
        """
        for item in sorted(sale.items, key=lambda i: str(i.product_id)):
            delta = -item.quantity if outgoing else item.quantity
            await self._stock_service.apply_movement(
                company_id=tenant.company_id,
                product_id=item.product_id,
                warehouse_id=sale.warehouse_id,
                delta=delta,
                movement_type=MovementType.SALE if outgoing else MovementType.RETURN,
                reference_type=ReferenceType.SALE,
                reference_id=sale.id,
                notes=notes,
                created_by=tenant.user_id,
            )


class CreateSaleUseCase(_SaleStockMixin):
    def __init__(
        self,
        sales: SaleRepository,
        products: ProductRepository,
        warehouses: WarehouseRepository,
        customers: CustomerRepository,
        stock_service: StockService,
    ) -> None:
        self._sales = sales
        self._products = products
        self._warehouses = warehouses
        self._customers = customers
        self._stock_service = stock_service

    async def execute(self, command: CreateSaleCommand, *, tenant: TenantContext) -> SaleDTO:
        warehouse = await self._warehouses.get_by_id(tenant.company_id, command.warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError()
        if not warehouse.is_active:
            raise InactiveWarehouseError(f"Warehouse '{warehouse.name}' is not active")

        if command.customer_id is not None:
            customer = await self._customers.get_by_id(tenant.company_id, command.customer_id)
            if customer is None:
                raise CustomerNotFoundError()
            if not customer.is_active:
                raise InactiveCustomerError(f"Customer '{customer.name}' is not active")

        sale_id = uuid.uuid4()
        items: list[SaleItem] = []
        for line in command.items:
            product = await self._products.get_by_id(tenant.company_id, line.product_id)
            if product is None:
                raise ProductNotFoundError(
                    "Product not found", details={"product_id": str(line.product_id)}
                )
            if not product.is_active:
                raise BusinessRuleError(
                    f"Product '{product.name}' is inactive and cannot be sold",
                    code="INACTIVE_PRODUCT",
                    details={"product_id": str(product.id)},
                )

            items.append(
                SaleItem(
                    company_id=tenant.company_id,
                    sale_id=sale_id,
                    product_id=product.id,
                    quantity=line.quantity,
                    unit_price=(
                        line.unit_price if line.unit_price is not None else product.sale_price
                    ),
                    discount=line.discount,
                    tax=line.tax,
                )
            )

        sale = Sale(
            id=sale_id,
            company_id=tenant.company_id,
            customer_id=command.customer_id,
            warehouse_id=command.warehouse_id,
            notes=command.notes,
            created_by=tenant.user_id,
            items=items,
        )

        if command.complete:
            sale.complete()

        created = await self._sales.add(sale)

        if command.complete:
            await self._move_stock(created, outgoing=True, tenant=tenant)

        return SaleDTO.model_validate(created, from_attributes=True)


class GetSaleUseCase:
    def __init__(self, sales: SaleRepository) -> None:
        self._sales = sales

    async def execute(self, sale_id: uuid.UUID, *, tenant: TenantContext) -> SaleDTO:
        sale = await self._sales.get_by_id(tenant.company_id, sale_id)
        if sale is None:
            raise SaleNotFoundError()
        return SaleDTO.model_validate(sale, from_attributes=True)


class ListSalesUseCase:
    def __init__(self, sales: SaleRepository) -> None:
        self._sales = sales

    async def execute(self, query: ListSalesQuery, *, tenant: TenantContext) -> SalePageDTO:
        result = await self._sales.list(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            status=query.status,
            customer_id=query.customer_id,
            warehouse_id=query.warehouse_id,
        )
        return SalePageDTO(
            items=[SaleDTO.model_validate(row, from_attributes=True) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class CompleteSaleUseCase(_SaleStockMixin):
    def __init__(self, sales: SaleRepository, stock_service: StockService) -> None:
        self._sales = sales
        self._stock_service = stock_service

    async def execute(self, sale_id: uuid.UUID, *, tenant: TenantContext) -> SaleDTO:
        sale = await self._sales.get_by_id(tenant.company_id, sale_id)
        if sale is None:
            raise SaleNotFoundError()

        sale.complete()
        await self._move_stock(sale, outgoing=True, tenant=tenant)
        updated = await self._sales.update_header(sale)
        return SaleDTO.model_validate(updated, from_attributes=True)


class CancelSaleUseCase(_SaleStockMixin):
    """A DRAFT sale is simply dropped; a COMPLETED one gives its stock back."""

    def __init__(self, sales: SaleRepository, stock_service: StockService) -> None:
        self._sales = sales
        self._stock_service = stock_service

    async def execute(self, sale_id: uuid.UUID, *, tenant: TenantContext) -> SaleDTO:
        sale = await self._sales.get_by_id(tenant.company_id, sale_id)
        if sale is None:
            raise SaleNotFoundError()

        restock = sale.affects_stock
        sale.cancel()
        if restock:
            await self._move_stock(sale, outgoing=False, tenant=tenant, notes="Sale cancelled")
        updated = await self._sales.update_header(sale)
        return SaleDTO.model_validate(updated, from_attributes=True)


class RefundSaleUseCase(_SaleStockMixin):
    def __init__(self, sales: SaleRepository, stock_service: StockService) -> None:
        self._sales = sales
        self._stock_service = stock_service

    async def execute(self, sale_id: uuid.UUID, *, tenant: TenantContext) -> SaleDTO:
        sale = await self._sales.get_by_id(tenant.company_id, sale_id)
        if sale is None:
            raise SaleNotFoundError()

        sale.refund()
        await self._move_stock(sale, outgoing=False, tenant=tenant, notes="Sale refunded")
        updated = await self._sales.update_header(sale)
        return SaleDTO.model_validate(updated, from_attributes=True)
