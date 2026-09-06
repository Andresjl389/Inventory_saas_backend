import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.products.entities.category import Category
from app.infrastructure.database.models.product import CategoryModel
from app.infrastructure.database.repositories.mappers import category_to_domain


class SqlAlchemyCategoryRepository:
    """Every statement filters by company_id explicitly. RLS enforces the same
    rule underneath -- belt and braces, per BACKEND.md section 24."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID, category_id: uuid.UUID) -> Category | None:
        stmt = select(CategoryModel).where(
            CategoryModel.id == category_id,
            CategoryModel.company_id == company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return category_to_domain(model) if model else None

    async def get_by_name(self, company_id: uuid.UUID, name: str) -> Category | None:
        stmt = select(CategoryModel).where(
            CategoryModel.company_id == company_id,
            CategoryModel.name == name,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return category_to_domain(model) if model else None

    async def list(self, company_id: uuid.UUID) -> list[Category]:
        stmt = (
            select(CategoryModel)
            .where(CategoryModel.company_id == company_id)
            .order_by(CategoryModel.name)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [category_to_domain(row) for row in rows]

    async def add(self, category: Category) -> Category:
        model = CategoryModel(
            id=category.id,
            company_id=category.company_id,
            name=category.name,
            description=category.description,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return category_to_domain(model)

    async def update(self, category: Category) -> Category:
        stmt = select(CategoryModel).where(
            CategoryModel.id == category.id,
            CategoryModel.company_id == category.company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Category {category.id} disappeared before update")
        model.name = category.name
        model.description = category.description
        await self._session.flush()
        return category_to_domain(model)

    async def delete(self, company_id: uuid.UUID, category_id: uuid.UUID) -> None:
        stmt = delete(CategoryModel).where(
            CategoryModel.id == category_id,
            CategoryModel.company_id == company_id,
        )
        await self._session.execute(stmt)
