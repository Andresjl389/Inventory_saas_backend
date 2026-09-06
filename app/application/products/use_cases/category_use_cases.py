import uuid

from app.application.products.dto.category import (
    CategoryDTO,
    CreateCategoryCommand,
    UpdateCategoryCommand,
)
from app.domain.products.entities.category import Category
from app.domain.products.exceptions import CategoryNotFoundError, DuplicateCategoryNameError
from app.domain.products.repositories.category_repository import CategoryRepository
from app.domain.tenants.tenant_context import TenantContext


class CreateCategoryUseCase:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def execute(
        self, command: CreateCategoryCommand, *, tenant: TenantContext
    ) -> CategoryDTO:
        name = command.name.strip()
        if await self._categories.get_by_name(tenant.company_id, name) is not None:
            raise DuplicateCategoryNameError()

        category = await self._categories.add(
            Category(company_id=tenant.company_id, name=name, description=command.description)
        )
        return CategoryDTO.model_validate(category, from_attributes=True)


class ListCategoriesUseCase:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def execute(self, tenant: TenantContext) -> list[CategoryDTO]:
        rows = await self._categories.list(tenant.company_id)
        return [CategoryDTO.model_validate(row, from_attributes=True) for row in rows]


class UpdateCategoryUseCase:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def execute(
        self,
        category_id: uuid.UUID,
        command: UpdateCategoryCommand,
        *,
        tenant: TenantContext,
    ) -> CategoryDTO:
        category = await self._categories.get_by_id(tenant.company_id, category_id)
        if category is None:
            raise CategoryNotFoundError()

        if command.name is not None:
            name = command.name.strip()
            clash = await self._categories.get_by_name(tenant.company_id, name)
            if clash is not None and clash.id != category.id:
                raise DuplicateCategoryNameError()
            category.rename(name)

        if command.description is not None:
            category.description = command.description
            category.touch()

        updated = await self._categories.update(category)
        return CategoryDTO.model_validate(updated, from_attributes=True)


class DeleteCategoryUseCase:
    def __init__(self, categories: CategoryRepository) -> None:
        self._categories = categories

    async def execute(self, category_id: uuid.UUID, *, tenant: TenantContext) -> None:
        category = await self._categories.get_by_id(tenant.company_id, category_id)
        if category is None:
            raise CategoryNotFoundError()
        # Products keep existing with category_id set to NULL (FK ON DELETE SET NULL).
        await self._categories.delete(tenant.company_id, category_id)
