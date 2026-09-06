import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.application.products.dto.product import (
    CreateProductCommand,
    ListProductsQuery,
    ProductDTO,
    ProductPageDTO,
    UpdateProductCommand,
)
from app.application.products.use_cases.product_use_cases import (
    CreateProductUseCase,
    DeactivateProductUseCase,
    GetProductUseCase,
    ListProductsUseCase,
    UpdateProductUseCase,
)
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import CategoryRepoDep, ProductRepoDep
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/products", tags=["products"])

ReadDep = Annotated[TenantContext, Depends(require_permission("products.read"))]
CreateDep = Annotated[TenantContext, Depends(require_permission("products.create"))]
UpdateDep = Annotated[TenantContext, Depends(require_permission("products.update"))]
DeleteDep = Annotated[TenantContext, Depends(require_permission("products.delete"))]


@router.get("", response_model=ProductPageDTO)
async def list_products(
    tenant: ReadDep,
    products: ProductRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    category_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> ProductPageDTO:
    query = ListProductsQuery(
        page=page, size=size, search=search, category_id=category_id, is_active=is_active
    )
    return await ListProductsUseCase(products).execute(query, tenant=tenant)


@router.post("", response_model=ProductDTO, status_code=status.HTTP_201_CREATED)
async def create_product(
    command: CreateProductCommand,
    tenant: CreateDep,
    products: ProductRepoDep,
    categories: CategoryRepoDep,
) -> ProductDTO:
    return await CreateProductUseCase(products, categories).execute(command, tenant=tenant)


@router.get("/{product_id}", response_model=ProductDTO)
async def get_product(
    product_id: uuid.UUID, tenant: ReadDep, products: ProductRepoDep
) -> ProductDTO:
    return await GetProductUseCase(products).execute(product_id, tenant=tenant)


@router.patch("/{product_id}", response_model=ProductDTO)
async def update_product(
    product_id: uuid.UUID,
    command: UpdateProductCommand,
    tenant: UpdateDep,
    products: ProductRepoDep,
    categories: CategoryRepoDep,
) -> ProductDTO:
    return await UpdateProductUseCase(products, categories).execute(
        product_id, command, tenant=tenant
    )


@router.delete("/{product_id}", response_model=ProductDTO, status_code=status.HTTP_200_OK)
async def deactivate_product(
    product_id: uuid.UUID, tenant: DeleteDep, products: ProductRepoDep
) -> ProductDTO:
    """Soft delete: sales and stock movements must keep referencing the product."""
    return await DeactivateProductUseCase(products).execute(product_id, tenant=tenant)
