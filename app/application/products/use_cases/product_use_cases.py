import uuid

from app.application.products.dto.product import (
    CreateProductCommand,
    ListProductsQuery,
    ProductDTO,
    ProductPageDTO,
    UpdateProductCommand,
)
from app.domain.products.entities.product import Product
from app.domain.products.exceptions import (
    CategoryNotFoundError,
    DuplicateBarcodeError,
    DuplicateSkuError,
    ProductNotFoundError,
)
from app.domain.products.repositories.category_repository import CategoryRepository
from app.domain.products.repositories.product_repository import ProductRepository
from app.domain.shared.pagination import Page
from app.domain.tenants.tenant_context import TenantContext


async def _assert_category_exists(
    categories: CategoryRepository, company_id: uuid.UUID, category_id: uuid.UUID | None
) -> None:
    if category_id is None:
        return
    if await categories.get_by_id(company_id, category_id) is None:
        raise CategoryNotFoundError()


class CreateProductUseCase:
    def __init__(self, products: ProductRepository, categories: CategoryRepository) -> None:
        self._products = products
        self._categories = categories

    async def execute(self, command: CreateProductCommand, *, tenant: TenantContext) -> ProductDTO:
        sku = command.sku.strip().upper()
        if await self._products.get_by_sku(tenant.company_id, sku) is not None:
            raise DuplicateSkuError()

        if command.barcode and await self._products.get_by_barcode(
            tenant.company_id, command.barcode
        ):
            raise DuplicateBarcodeError()

        await _assert_category_exists(self._categories, tenant.company_id, command.category_id)

        product = await self._products.add(
            Product(
                company_id=tenant.company_id,
                category_id=command.category_id,
                name=command.name.strip(),
                description=command.description,
                sku=sku,
                barcode=command.barcode,
                cost_price=command.cost_price,
                sale_price=command.sale_price,
            )
        )
        return ProductDTO.model_validate(product, from_attributes=True)


class GetProductUseCase:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    async def execute(self, product_id: uuid.UUID, *, tenant: TenantContext) -> ProductDTO:
        product = await self._products.get_by_id(tenant.company_id, product_id)
        if product is None:
            raise ProductNotFoundError()
        return ProductDTO.model_validate(product, from_attributes=True)


class ListProductsUseCase:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    async def execute(self, query: ListProductsQuery, *, tenant: TenantContext) -> ProductPageDTO:
        result = await self._products.list(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            search=query.search,
            category_id=query.category_id,
            is_active=query.is_active,
        )
        return ProductPageDTO(
            items=[ProductDTO.model_validate(p, from_attributes=True) for p in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class UpdateProductUseCase:
    def __init__(self, products: ProductRepository, categories: CategoryRepository) -> None:
        self._products = products
        self._categories = categories

    async def execute(
        self,
        product_id: uuid.UUID,
        command: UpdateProductCommand,
        *,
        tenant: TenantContext,
    ) -> ProductDTO:
        product = await self._products.get_by_id(tenant.company_id, product_id)
        if product is None:
            raise ProductNotFoundError()

        if command.sku is not None:
            sku = command.sku.strip().upper()
            clash = await self._products.get_by_sku(tenant.company_id, sku)
            if clash is not None and clash.id != product.id:
                raise DuplicateSkuError()
            product.sku = sku

        if command.barcode is not None:
            clash = await self._products.get_by_barcode(tenant.company_id, command.barcode)
            if clash is not None and clash.id != product.id:
                raise DuplicateBarcodeError()
            product.barcode = command.barcode

        if command.category_id is not None:
            await _assert_category_exists(self._categories, tenant.company_id, command.category_id)
            product.category_id = command.category_id

        if command.name is not None:
            product.name = command.name.strip()
        if command.description is not None:
            product.description = command.description
        if command.is_active is not None:
            product.is_active = command.is_active

        product.update_prices(cost_price=command.cost_price, sale_price=command.sale_price)

        updated = await self._products.update(product)
        return ProductDTO.model_validate(updated, from_attributes=True)


class DeactivateProductUseCase:
    """Products are never hard-deleted: sales and stock movements reference them."""

    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    async def execute(self, product_id: uuid.UUID, *, tenant: TenantContext) -> ProductDTO:
        product = await self._products.get_by_id(tenant.company_id, product_id)
        if product is None:
            raise ProductNotFoundError()
        product.deactivate()
        updated = await self._products.update(product)
        return ProductDTO.model_validate(updated, from_attributes=True)
