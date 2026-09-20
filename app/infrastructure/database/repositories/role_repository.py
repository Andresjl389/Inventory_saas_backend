import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.authorization.entities.role import Permission, Role
from app.infrastructure.database.models.authorization import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
)
from app.infrastructure.database.models.company import CompanyMemberModel
from app.infrastructure.database.repositories.mappers import permission_to_domain, role_to_domain


class SqlAlchemyRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def permissions_of(self, role_id: uuid.UUID) -> frozenset[str]:
        stmt = (
            select(PermissionModel.code)
            .join(RolePermissionModel, RolePermissionModel.permission_id == PermissionModel.id)
            .where(RolePermissionModel.role_id == role_id)
        )
        return frozenset((await self._session.execute(stmt)).scalars().all())

    async def get_by_id(self, role_id: uuid.UUID) -> Role | None:
        model = await self._session.get(RoleModel, role_id)
        if model is None:
            return None
        return role_to_domain(model, await self.permissions_of(model.id))

    async def get_by_code(self, code: str, *, company_id: uuid.UUID | None) -> Role | None:
        stmt = select(RoleModel).where(RoleModel.code == code.strip().upper())
        stmt = stmt.where(
            RoleModel.company_id.is_(None)
            if company_id is None
            else RoleModel.company_id == company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        return role_to_domain(model, await self.permissions_of(model.id))

    async def resolve_for_company(self, code: str, company_id: uuid.UUID) -> Role | None:
        """A company's own role wins over the system role of the same code, so a
        tenant can tighten (or widen) a built-in role for itself."""
        own = await self.get_by_code(code, company_id=company_id)
        return own or await self.get_by_code(code, company_id=None)

    async def list_for_company(self, company_id: uuid.UUID) -> list[Role]:
        stmt = (
            select(RoleModel)
            .where((RoleModel.company_id == company_id) | RoleModel.company_id.is_(None))
            .order_by(RoleModel.is_system.desc(), RoleModel.code)
        )
        models = (await self._session.execute(stmt)).scalars().all()

        # One query for all the permissions instead of one per role.
        role_ids = [model.id for model in models]
        grants = (
            await self._session.execute(
                select(RolePermissionModel.role_id, PermissionModel.code)
                .join(PermissionModel, PermissionModel.id == RolePermissionModel.permission_id)
                .where(RolePermissionModel.role_id.in_(role_ids))
            )
        ).all()
        by_role: dict[uuid.UUID, set[str]] = {}
        for role_id, code in grants:
            by_role.setdefault(role_id, set()).add(code)

        return [role_to_domain(model, frozenset(by_role.get(model.id, set()))) for model in models]

    async def add(self, role: Role) -> Role:
        model = RoleModel(
            id=role.id,
            company_id=role.company_id,
            code=role.code,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
        )
        self._session.add(model)
        await self._session.flush()
        await self._set_permissions(model.id, role.permissions)
        await self._session.refresh(model)
        return role_to_domain(model, role.permissions)

    async def update(self, role: Role) -> Role:
        model = await self._session.get(RoleModel, role.id)
        if model is None:
            raise LookupError(f"Role {role.id} disappeared before update")
        model.name = role.name
        model.description = role.description
        await self._session.flush()
        await self._set_permissions(model.id, role.permissions)
        return role_to_domain(model, role.permissions)

    async def delete(self, role_id: uuid.UUID) -> None:
        await self._session.execute(delete(RoleModel).where(RoleModel.id == role_id))

    async def count_members(self, role_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(CompanyMemberModel)
            .where(CompanyMemberModel.role_id == role_id)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def _set_permissions(self, role_id: uuid.UUID, codes: frozenset[str]) -> None:
        """Replace the grants wholesale: the caller sends the full set it wants."""
        await self._session.execute(
            delete(RolePermissionModel).where(RolePermissionModel.role_id == role_id)
        )
        if not codes:
            return
        permission_ids = (
            (
                await self._session.execute(
                    select(PermissionModel.id).where(PermissionModel.code.in_(sorted(codes)))
                )
            )
            .scalars()
            .all()
        )
        for permission_id in permission_ids:
            self._session.add(RolePermissionModel(role_id=role_id, permission_id=permission_id))
        await self._session.flush()


class SqlAlchemyPermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Permission]:
        stmt = select(PermissionModel).order_by(PermissionModel.module, PermissionModel.code)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [permission_to_domain(row) for row in rows]
