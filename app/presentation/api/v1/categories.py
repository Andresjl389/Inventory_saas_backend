import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.application.products.dto.category import (
    CategoryDTO,
    CreateCategoryCommand,
    UpdateCategoryCommand,
)
from app.application.products.use_cases.category_use_cases import (
    CreateCategoryUseCase,
    DeleteCategoryUseCase,
    ListCategoriesUseCase,
    UpdateCategoryUseCase,
)
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import CategoryRepoDep
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/categories", tags=["categories"])

ReadDep = Annotated[TenantContext, Depends(require_permission("categories.read"))]
WriteDep = Annotated[TenantContext, Depends(require_permission("categories.write"))]


@router.get("", response_model=list[CategoryDTO])
async def list_categories(tenant: ReadDep, categories: CategoryRepoDep) -> list[CategoryDTO]:
    return await ListCategoriesUseCase(categories).execute(tenant)


@router.post("", response_model=CategoryDTO, status_code=status.HTTP_201_CREATED)
async def create_category(
    command: CreateCategoryCommand, tenant: WriteDep, categories: CategoryRepoDep
) -> CategoryDTO:
    return await CreateCategoryUseCase(categories).execute(command, tenant=tenant)


@router.patch("/{category_id}", response_model=CategoryDTO)
async def update_category(
    category_id: uuid.UUID,
    command: UpdateCategoryCommand,
    tenant: WriteDep,
    categories: CategoryRepoDep,
) -> CategoryDTO:
    return await UpdateCategoryUseCase(categories).execute(category_id, command, tenant=tenant)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID, tenant: WriteDep, categories: CategoryRepoDep
) -> None:
    await DeleteCategoryUseCase(categories).execute(category_id, tenant=tenant)
