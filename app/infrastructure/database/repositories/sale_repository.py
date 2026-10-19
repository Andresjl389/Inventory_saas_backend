import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.sales.entities.sale import Sale, SaleStatus
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.sale import SaleItemModel, SaleModel
from app.infrastructure.database.repositories.mappers import sale_to_domain


class SqlAlchemySaleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID, sale_id: uuid.UUID) -> Sale | None:
        stmt = select(SaleModel).where(SaleModel.id == sale_id, SaleModel.company_id == company_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return sale_to_domain(model) if model else None

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        status: SaleStatus | None = None,
        customer_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> PaginatedResult[Sale]:
        filters = [SaleModel.company_id == company_id]
        if status is not None:
            filters.append(SaleModel.status == status)
        if customer_id is not None:
            filters.append(SaleModel.customer_id == customer_id)
        if warehouse_id is not None:
            filters.append(SaleModel.warehouse_id == warehouse_id)

        total = (
            await self._session.execute(select(func.count()).select_from(SaleModel).where(*filters))
        ).scalar_one()

        stmt = (
            select(SaleModel)
            .where(*filters)
            .order_by(SaleModel.created_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(items=[sale_to_domain(row) for row in rows], total=total, page=page)

    async def add(self, sale: Sale) -> Sale:
        model = SaleModel(
            id=sale.id,
            company_id=sale.company_id,
            customer_id=sale.customer_id,
            warehouse_id=sale.warehouse_id,
            status=sale.status,
            payment_method=sale.payment_method,
            amount_paid=sale.amount_paid,
            subtotal=sale.subtotal,
            discount=sale.discount,
            tax=sale.tax,
            total=sale.total,
            notes=sale.notes,
            created_by=sale.created_by,
            items=[
                SaleItemModel(
                    id=item.id,
                    company_id=item.company_id,
                    sale_id=sale.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    discount=item.discount,
                    tax=item.tax,
                    total=item.total,
                )
                for item in sale.items
            ],
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return sale_to_domain(model)

    async def update_header(self, sale: Sale) -> Sale:
        stmt = select(SaleModel).where(
            SaleModel.id == sale.id, SaleModel.company_id == sale.company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Sale {sale.id} disappeared before update")
        model.status = sale.status
        model.customer_id = sale.customer_id
        model.payment_method = sale.payment_method
        model.amount_paid = sale.amount_paid
        model.subtotal = sale.subtotal
        model.discount = sale.discount
        model.tax = sale.tax
        model.total = sale.total
        model.notes = sale.notes
        await self._session.flush()
        return sale_to_domain(model)
