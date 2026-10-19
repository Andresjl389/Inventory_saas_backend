"""Sales use cases.

Completing a sale is the transaction sketched in BACKEND.md section 28: lock
stock, check availability, write the movements, update the cached quantities.
Every step runs inside the request transaction, so any failure rolls the whole
sale back -- there is no state where stock left the warehouse but the sale did
not record it.
"""

import uuid

from app.application.credit.services.credit_service import CreditService
from app.application.inventory.services.stock_service import StockService
from app.application.sales.dto.sale import (
    CreateSaleCommand,
    ListSalesQuery,
    SaleDTO,
    SalePageDTO,
)
from app.domain.credit.entities.account import EntryType
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


def _to_dto(sale: Sale) -> SaleDTO:
    dto = SaleDTO.model_validate(sale, from_attributes=True)
    dto.outstanding = sale.outstanding
    return dto


class _SaleCreditMixin:
    """Una venta fiada mueve la cuenta del cliente en la misma transacción que
    el stock: o quedan los dos registrados o no queda ninguno."""

    _credit_service: CreditService | None = None

    async def _charge_credit(self, sale: Sale, *, tenant, credit_limit=None) -> None:
        if self._credit_service is None or not sale.is_on_credit:
            return
        await self._credit_service.apply_entry(
            company_id=tenant.company_id,
            customer_id=sale.customer_id,
            amount=sale.outstanding,
            entry_type=EntryType.SALE,
            reference_id=sale.id,
            notes="Venta fiada",
            created_by=tenant.user_id,
            credit_limit=credit_limit,
        )

    async def _release_credit(self, sale: Sale, *, tenant, reason: str) -> None:
        """Al cancelar o devolver una venta fiada, la deuda se va con ella."""
        if self._credit_service is None or not sale.is_on_credit:
            return
        await self._credit_service.apply_entry(
            company_id=tenant.company_id,
            customer_id=sale.customer_id,
            amount=-sale.outstanding,
            entry_type=EntryType.SALE_REVERSED,
            reference_id=sale.id,
            notes=reason,
            created_by=tenant.user_id,
        )


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


class CreateSaleUseCase(_SaleStockMixin, _SaleCreditMixin):
    def __init__(
        self,
        sales: SaleRepository,
        products: ProductRepository,
        warehouses: WarehouseRepository,
        customers: CustomerRepository,
        stock_service: StockService,
        credit_service: CreditService | None = None,
    ) -> None:
        self._sales = sales
        self._products = products
        self._warehouses = warehouses
        self._customers = customers
        self._stock_service = stock_service
        self._credit_service = credit_service

    async def execute(self, command: CreateSaleCommand, *, tenant: TenantContext) -> SaleDTO:
        warehouse = await self._warehouses.get_by_id(tenant.company_id, command.warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError()
        if not warehouse.is_active:
            raise InactiveWarehouseError(f"Warehouse '{warehouse.name}' is not active")

        customer = None
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

        # Liquidar antes de completar: así "fiar sin cliente" y "pagar de más"
        # se rechazan antes de tocar el stock.
        sale.settle(command.payment_method, command.amount_paid)

        if command.complete:
            sale.complete()

        created = await self._sales.add(sale)

        if command.complete:
            await self._move_stock(created, outgoing=True, tenant=tenant)
            await self._charge_credit(
                created,
                tenant=tenant,
                credit_limit=customer.credit_limit if customer else None,
            )

        return _to_dto(created)


class GetSaleUseCase:
    def __init__(self, sales: SaleRepository) -> None:
        self._sales = sales

    async def execute(self, sale_id: uuid.UUID, *, tenant: TenantContext) -> SaleDTO:
        sale = await self._sales.get_by_id(tenant.company_id, sale_id)
        if sale is None:
            raise SaleNotFoundError()
        return _to_dto(sale)


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
            items=[_to_dto(row) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class CompleteSaleUseCase(_SaleStockMixin, _SaleCreditMixin):
    def __init__(
        self,
        sales: SaleRepository,
        stock_service: StockService,
        credit_service: CreditService | None = None,
        customers: CustomerRepository | None = None,
    ) -> None:
        self._sales = sales
        self._stock_service = stock_service
        self._credit_service = credit_service
        self._customers = customers

    async def execute(self, sale_id: uuid.UUID, *, tenant: TenantContext) -> SaleDTO:
        sale = await self._sales.get_by_id(tenant.company_id, sale_id)
        if sale is None:
            raise SaleNotFoundError()

        sale.complete()
        await self._move_stock(sale, outgoing=True, tenant=tenant)

        credit_limit = None
        if sale.is_on_credit and self._customers is not None:
            customer = await self._customers.get_by_id(tenant.company_id, sale.customer_id)
            credit_limit = customer.credit_limit if customer else None
        await self._charge_credit(sale, tenant=tenant, credit_limit=credit_limit)

        updated = await self._sales.update_header(sale)
        return _to_dto(updated)


class CancelSaleUseCase(_SaleStockMixin, _SaleCreditMixin):
    """Una venta DRAFT simplemente se descarta; una COMPLETED devuelve su stock
    y, si quedó fiada, borra la deuda que dejó."""

    def __init__(
        self,
        sales: SaleRepository,
        stock_service: StockService,
        credit_service: CreditService | None = None,
    ) -> None:
        self._sales = sales
        self._stock_service = stock_service
        self._credit_service = credit_service

    async def execute(self, sale_id: uuid.UUID, *, tenant: TenantContext) -> SaleDTO:
        sale = await self._sales.get_by_id(tenant.company_id, sale_id)
        if sale is None:
            raise SaleNotFoundError()

        was_completed = sale.affects_stock
        sale.cancel()
        if was_completed:
            await self._move_stock(sale, outgoing=False, tenant=tenant, notes="Sale cancelled")
            await self._release_credit(sale, tenant=tenant, reason="Venta cancelada")
        updated = await self._sales.update_header(sale)
        return _to_dto(updated)


class RefundSaleUseCase(_SaleStockMixin, _SaleCreditMixin):
    def __init__(
        self,
        sales: SaleRepository,
        stock_service: StockService,
        credit_service: CreditService | None = None,
    ) -> None:
        self._sales = sales
        self._stock_service = stock_service
        self._credit_service = credit_service

    async def execute(self, sale_id: uuid.UUID, *, tenant: TenantContext) -> SaleDTO:
        sale = await self._sales.get_by_id(tenant.company_id, sale_id)
        if sale is None:
            raise SaleNotFoundError()

        sale.refund()
        await self._move_stock(sale, outgoing=False, tenant=tenant, notes="Sale refunded")
        await self._release_credit(sale, tenant=tenant, reason="Venta devuelta")
        updated = await self._sales.update_header(sale)
        return _to_dto(updated)
