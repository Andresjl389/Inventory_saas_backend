import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenants.entities.company_member import CompanyMember
from app.infrastructure.database.models.authorization import RoleModel
from app.infrastructure.database.models.company import CompanyMemberModel
from app.infrastructure.database.repositories.mappers import member_to_domain


class SqlAlchemyCompanyMemberRepository:
    """Every read joins `roles` so callers get the role *code* alongside the id
    without a second round trip."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _with_role():
        return select(CompanyMemberModel, RoleModel.code).join(
            RoleModel, RoleModel.id == CompanyMemberModel.role_id
        )

    async def get(self, company_id: uuid.UUID, user_id: uuid.UUID) -> CompanyMember | None:
        stmt = self._with_role().where(
            CompanyMemberModel.company_id == company_id,
            CompanyMemberModel.user_id == user_id,
        )
        row = (await self._session.execute(stmt)).one_or_none()
        return member_to_domain(row[0], row[1]) if row else None

    async def list_by_company(self, company_id: uuid.UUID) -> list[CompanyMember]:
        stmt = (
            self._with_role()
            .where(CompanyMemberModel.company_id == company_id)
            .order_by(CompanyMemberModel.created_at)
        )
        rows = (await self._session.execute(stmt)).all()
        return [member_to_domain(model, code) for model, code in rows]

    async def list_by_user(self, user_id: uuid.UUID) -> list[CompanyMember]:
        stmt = self._with_role().where(CompanyMemberModel.user_id == user_id)
        rows = (await self._session.execute(stmt)).all()
        return [member_to_domain(model, code) for model, code in rows]

    async def add(self, member: CompanyMember) -> CompanyMember:
        model = CompanyMemberModel(
            id=member.id,
            company_id=member.company_id,
            user_id=member.user_id,
            role_id=member.role_id,
            is_active=member.is_active,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return member_to_domain(model, member.role_code)

    async def update(self, member: CompanyMember) -> CompanyMember:
        model = await self._session.get(CompanyMemberModel, member.id)
        if model is None:
            raise LookupError(f"Membership {member.id} disappeared before update")
        model.role_id = member.role_id
        model.is_active = member.is_active
        await self._session.flush()
        return member_to_domain(model, member.role_code)
