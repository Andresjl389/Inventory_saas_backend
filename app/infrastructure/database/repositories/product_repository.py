import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.products.entities.product import Product
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.product import ProductModel
from app.infrastructure.database.repositories.mappers import product_to_domain


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID, product_id: uuid.UUID) -> Product | None:
        stmt = select(ProductModel).where(
            ProductModel.id == product_id,
            ProductModel.company_id == company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return product_to_domain(model) if model else None

    async def get_by_sku(self, company_id: uuid.UUID, sku: str) -> Product | None:
        stmt = select(ProductModel).where(
            ProductModel.company_id == company_id,
            ProductModel.sku == sku.strip().upper(),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return product_to_domain(model) if model else None

    async def get_by_barcode(self, company_id: uuid.UUID, barcode: str) -> Product | None:
        stmt = select(ProductModel).where(
            ProductModel.company_id == company_id,
            ProductModel.barcode == barcode,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return product_to_domain(model) if model else None

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        search: str | None = None,
        category_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResult[Product]:
        filters = [ProductModel.company_id == company_id]
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    ProductModel.name.ilike(pattern),
                    ProductModel.sku.ilike(pattern),
                    ProductModel.barcode.ilike(pattern),
                )
            )
        if category_id is not None:
            filters.append(ProductModel.category_id == category_id)
        if is_active is not None:
            filters.append(ProductModel.is_active.is_(is_active))

        total = (
            await self._session.execute(
                select(func.count()).select_from(ProductModel).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(ProductModel)
            .where(*filters)
            .order_by(ProductModel.created_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[product_to_domain(row) for row in rows],
            total=total,
            page=page,
        )

    async def add(self, product: Product) -> Product:
        model = ProductModel(
            id=product.id,
            company_id=product.company_id,
            category_id=product.category_id,
            name=product.name,
            description=product.description,
            sku=product.sku,
            barcode=product.barcode,
            cost_price=product.cost_price,
            sale_price=product.sale_price,
            is_active=product.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return product_to_domain(model)

    async def update(self, product: Product) -> Product:
        stmt = select(ProductModel).where(
            ProductModel.id == product.id,
            ProductModel.company_id == product.company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Product {product.id} disappeared before update")
        model.category_id = product.category_id
        model.name = product.name
        model.description = product.description
        model.sku = product.sku
        model.barcode = product.barcode
        model.cost_price = product.cost_price
        model.sale_price = product.sale_price
        model.is_active = product.is_active
        await self._session.flush()
        return product_to_domain(model)
