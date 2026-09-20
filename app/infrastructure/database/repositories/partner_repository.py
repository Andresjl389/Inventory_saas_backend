"""Customer and supplier repositories.

The two tables have identical access patterns today, so the SQL lives once in
`_PartyRepository`; the subclasses bind it to a model and a mapper. They still
satisfy two separate domain ports, so the implementations can diverge the day
the tables do.
"""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.customers.entities.customer import Customer
from app.domain.shared.document import DocumentType
from app.domain.shared.pagination import Page, PaginatedResult
from app.domain.suppliers.entities.supplier import Supplier
from app.infrastructure.database.models.partner import CustomerModel, SupplierModel
from app.infrastructure.database.repositories.mappers import customer_to_domain, supplier_to_domain

_WRITABLE_FIELDS = (
    "name",
    "document_type",
    "document_number",
    "email",
    "phone",
    "address",
    "is_active",
)


class _PartyRepository:
    model: Any
    to_domain: Any

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID, entity_id: uuid.UUID) -> Any | None:
        stmt = select(self.model).where(
            self.model.id == entity_id, self.model.company_id == company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self.to_domain(model) if model else None

    async def get_by_document(
        self, company_id: uuid.UUID, document_type: DocumentType, document_number: str
    ) -> Any | None:
        stmt = select(self.model).where(
            self.model.company_id == company_id,
            self.model.document_type == document_type,
            self.model.document_number == document_number,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self.to_domain(model) if model else None

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResult[Any]:
        filters = [self.model.company_id == company_id]
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    self.model.name.ilike(pattern),
                    self.model.document_number.ilike(pattern),
                    self.model.email.ilike(pattern),
                )
            )
        if is_active is not None:
            filters.append(self.model.is_active.is_(is_active))

        total = (
            await self._session.execute(
                select(func.count()).select_from(self.model).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(self.model)
            .where(*filters)
            .order_by(self.model.name)
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(items=[self.to_domain(row) for row in rows], total=total, page=page)

    async def add(self, entity: Any) -> Any:
        model = self.model(
            id=entity.id,
            company_id=entity.company_id,
            **{field: getattr(entity, field) for field in _WRITABLE_FIELDS},
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self.to_domain(model)

    async def update(self, entity: Any) -> Any:
        stmt = select(self.model).where(
            self.model.id == entity.id, self.model.company_id == entity.company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"{self.model.__name__} {entity.id} disappeared before update")
        for field in _WRITABLE_FIELDS:
            setattr(model, field, getattr(entity, field))
        await self._session.flush()
        return self.to_domain(model)


class SqlAlchemyCustomerRepository(_PartyRepository):
    model = CustomerModel
    to_domain = staticmethod(customer_to_domain)

    async def get_by_id(self, company_id: uuid.UUID, customer_id: uuid.UUID) -> Customer | None:
        return await super().get_by_id(company_id, customer_id)


class SqlAlchemySupplierRepository(_PartyRepository):
    model = SupplierModel
    to_domain = staticmethod(supplier_to_domain)

    async def get_by_id(self, company_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier | None:
        return await super().get_by_id(company_id, supplier_id)
