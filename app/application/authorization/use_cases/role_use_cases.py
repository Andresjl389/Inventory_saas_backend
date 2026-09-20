"""Managing roles inside a company.

System roles are read-only here: a company that wants OWNER-minus-something
clones it into a role of its own. That keeps the built-ins identical across
tenants, which is what makes them safe to reason about.
"""

import uuid

from app.application.authorization.dto.role import (
    CreateRoleCommand,
    PermissionDTO,
    RoleDTO,
    UpdateRoleCommand,
)
from app.domain.authorization.entities.role import Role
from app.domain.authorization.exceptions import (
    DuplicateRoleCodeError,
    RoleInUseError,
    RoleNotFoundError,
    SystemRoleImmutableError,
    UnknownPermissionError,
)
from app.domain.authorization.permissions import ALL_CODES, WILDCARD
from app.domain.authorization.repositories.role_repository import (
    PermissionRepository,
    RoleRepository,
)
from app.domain.tenants.tenant_context import TenantContext


def _validate_permissions(codes: list[str], *, tenant: TenantContext) -> frozenset[str]:
    requested = frozenset(codes)
    unknown = requested - ALL_CODES
    if unknown:
        raise UnknownPermissionError(
            f"Unknown permission codes: {', '.join(sorted(unknown))}",
            details={"unknown": sorted(unknown)},
        )
    if WILDCARD in requested and not tenant.has_permission(WILDCARD):
        # Otherwise an ADMIN could mint a role more powerful than their own and
        # assign it to themselves.
        raise UnknownPermissionError(
            "Only an owner can grant full access", code="CANNOT_GRANT_WILDCARD"
        )
    return requested


def _to_dto(role: Role) -> RoleDTO:
    return RoleDTO(
        id=role.id,
        company_id=role.company_id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=sorted(role.permissions),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


class ListRolesUseCase:
    """System roles plus the company's own."""

    def __init__(self, roles: RoleRepository) -> None:
        self._roles = roles

    async def execute(self, *, tenant: TenantContext) -> list[RoleDTO]:
        return [_to_dto(role) for role in await self._roles.list_for_company(tenant.company_id)]


class ListPermissionsUseCase:
    def __init__(self, permissions: PermissionRepository) -> None:
        self._permissions = permissions

    async def execute(self) -> list[PermissionDTO]:
        return [
            PermissionDTO.model_validate(item, from_attributes=True)
            for item in await self._permissions.list_all()
        ]


class CreateRoleUseCase:
    def __init__(self, roles: RoleRepository) -> None:
        self._roles = roles

    async def execute(self, command: CreateRoleCommand, *, tenant: TenantContext) -> RoleDTO:
        role = Role(
            company_id=tenant.company_id,
            code=command.code,
            name=command.name.strip(),
            description=command.description,
            is_system=False,
            permissions=_validate_permissions(command.permissions, tenant=tenant),
        )

        if await self._roles.get_by_code(role.code, company_id=tenant.company_id) is not None:
            raise DuplicateRoleCodeError()
        if await self._roles.get_by_code(role.code, company_id=None) is not None:
            raise DuplicateRoleCodeError(f"'{role.code}' is a built-in role code; pick another")

        return _to_dto(await self._roles.add(role))


class UpdateRoleUseCase:
    def __init__(self, roles: RoleRepository) -> None:
        self._roles = roles

    async def execute(
        self, role_id: uuid.UUID, command: UpdateRoleCommand, *, tenant: TenantContext
    ) -> RoleDTO:
        role = await self._roles.get_by_id(role_id)
        if role is None or (role.company_id not in (None, tenant.company_id)):
            raise RoleNotFoundError()
        if role.is_system:
            raise SystemRoleImmutableError(
                "Built-in roles are shared by every company. Create a custom role instead."
            )

        if command.name is not None:
            role.name = command.name.strip()
        if command.description is not None:
            role.description = command.description
        if command.permissions is not None:
            role.replace_permissions(_validate_permissions(command.permissions, tenant=tenant))
        role.touch()

        return _to_dto(await self._roles.update(role))


class DeleteRoleUseCase:
    def __init__(self, roles: RoleRepository) -> None:
        self._roles = roles

    async def execute(self, role_id: uuid.UUID, *, tenant: TenantContext) -> None:
        role = await self._roles.get_by_id(role_id)
        if role is None or role.company_id != tenant.company_id:
            raise RoleNotFoundError()
        if role.is_system:
            raise SystemRoleImmutableError()

        members = await self._roles.count_members(role_id)
        if members:
            raise RoleInUseError(
                f"{members} member(s) still hold this role; move them first",
                details={"members": members},
            )

        await self._roles.delete(role_id)
