import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenants.entities.company import Company
from app.infrastructure.database.models.company import CompanyMemberModel, CompanyModel
from app.infrastructure.database.repositories.mappers import company_to_domain


class SqlAlchemyCompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID) -> Company | None:
        model = await self._session.get(CompanyModel, company_id)
        return company_to_domain(model) if model else None

    async def add(self, company: Company) -> Company:
        model = CompanyModel(
            id=company.id,
            name=company.name,
            legal_name=company.legal_name,
            document_type=company.document_type,
            document_number=company.document_number,
            email=company.email,
            phone=company.phone,
            status=company.status,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return company_to_domain(model)

    async def update(self, company: Company) -> Company:
        model = await self._session.get(CompanyModel, company.id)
        if model is None:
            raise LookupError(f"Company {company.id} disappeared before update")
        model.name = company.name
        model.legal_name = company.legal_name
        model.document_type = company.document_type
        model.document_number = company.document_number
        model.email = company.email
        model.phone = company.phone
        model.status = company.status
        await self._session.flush()
        return company_to_domain(model)

    async def list_for_user(self, user_id: uuid.UUID) -> list[Company]:
        stmt = (
            select(CompanyModel)
            .join(CompanyMemberModel, CompanyMemberModel.company_id == CompanyModel.id)
            .where(
                CompanyMemberModel.user_id == user_id,
                CompanyMemberModel.is_active.is_(True),
            )
            .order_by(CompanyModel.name)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [company_to_domain(row) for row in rows]
