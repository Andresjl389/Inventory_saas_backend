import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.purchases.entities.purchase import Purchase, PurchaseStatus
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.purchase import PurchaseItemModel, PurchaseModel
from app.infrastructure.database.repositories.mappers import purchase_to_domain


class SqlAlchemyPurchaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID, purchase_id: uuid.UUID) -> Purchase | None:
        stmt = select(PurchaseModel).where(
            PurchaseModel.id == purchase_id, PurchaseModel.company_id == company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return purchase_to_domain(model) if model else None

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        status: PurchaseStatus | None = None,
        supplier_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> PaginatedResult[Purchase]:
        filters = [PurchaseModel.company_id == company_id]
        if status is not None:
            filters.append(PurchaseModel.status == status)
        if supplier_id is not None:
            filters.append(PurchaseModel.supplier_id == supplier_id)
        if warehouse_id is not None:
            filters.append(PurchaseModel.warehouse_id == warehouse_id)

        total = (
            await self._session.execute(
                select(func.count()).select_from(PurchaseModel).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(PurchaseModel)
            .where(*filters)
            .order_by(PurchaseModel.created_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[purchase_to_domain(row) for row in rows], total=total, page=page
        )

    async def add(self, purchase: Purchase) -> Purchase:
        model = PurchaseModel(
            id=purchase.id,
            company_id=purchase.company_id,
            supplier_id=purchase.supplier_id,
            warehouse_id=purchase.warehouse_id,
            status=purchase.status,
            subtotal=purchase.subtotal,
            discount=purchase.discount,
            tax=purchase.tax,
            total=purchase.total,
            notes=purchase.notes,
            created_by=purchase.created_by,
            items=[
                PurchaseItemModel(
                    id=item.id,
                    company_id=item.company_id,
                    purchase_id=purchase.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    discount=item.discount,
                    tax=item.tax,
                    total=item.total,
                )
                for item in purchase.items
            ],
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return purchase_to_domain(model)

    async def update_header(self, purchase: Purchase) -> Purchase:
        stmt = select(PurchaseModel).where(
            PurchaseModel.id == purchase.id, PurchaseModel.company_id == purchase.company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Purchase {purchase.id} disappeared before update")
        model.status = purchase.status
        model.supplier_id = purchase.supplier_id
        model.subtotal = purchase.subtotal
        model.discount = purchase.discount
        model.tax = purchase.tax
        model.total = purchase.total
        model.notes = purchase.notes
        await self._session.flush()
        return purchase_to_domain(model)
