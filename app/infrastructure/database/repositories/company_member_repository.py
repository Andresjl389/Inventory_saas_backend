import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenants.entities.company_member import CompanyMember
from app.infrastructure.database.models.company import CompanyMemberModel
from app.infrastructure.database.repositories.mappers import member_to_domain


class SqlAlchemyCompanyMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, company_id: uuid.UUID, user_id: uuid.UUID) -> CompanyMember | None:
        stmt = select(CompanyMemberModel).where(
            CompanyMemberModel.company_id == company_id,
            CompanyMemberModel.user_id == user_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return member_to_domain(model) if model else None

    async def list_by_company(self, company_id: uuid.UUID) -> list[CompanyMember]:
        stmt = (
            select(CompanyMemberModel)
            .where(CompanyMemberModel.company_id == company_id)
            .order_by(CompanyMemberModel.created_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [member_to_domain(row) for row in rows]

    async def list_by_user(self, user_id: uuid.UUID) -> list[CompanyMember]:
        stmt = select(CompanyMemberModel).where(CompanyMemberModel.user_id == user_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [member_to_domain(row) for row in rows]

    async def add(self, member: CompanyMember) -> CompanyMember:
        model = CompanyMemberModel(
            id=member.id,
            company_id=member.company_id,
            user_id=member.user_id,
            role=member.role,
            is_active=member.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return member_to_domain(model)

    async def update(self, member: CompanyMember) -> CompanyMember:
        model = await self._session.get(CompanyMemberModel, member.id)
        if model is None:
            raise LookupError(f"Membership {member.id} disappeared before update")
        model.role = member.role
        model.is_active = member.is_active
        await self._session.flush()
        return member_to_domain(model)
