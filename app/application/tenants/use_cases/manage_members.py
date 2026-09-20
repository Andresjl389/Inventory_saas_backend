import uuid

from app.application.tenants.dto.company import (
    AddMemberCommand,
    ChangeMemberRoleCommand,
    CompanyMemberDTO,
)
from app.domain.authorization.exceptions import RoleNotFoundError
from app.domain.authorization.repositories.role_repository import RoleRepository
from app.domain.identity.exceptions import UserNotFoundError
from app.domain.identity.repositories.user_repository import UserRepository
from app.domain.tenants.entities.company_member import CompanyMember
from app.domain.tenants.exceptions import (
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
)
from app.domain.tenants.repositories.company_member_repository import CompanyMemberRepository
from app.domain.tenants.tenant_context import TenantContext
from app.shared.exceptions import BusinessRuleError


async def _resolve_role(roles: RoleRepository, code: str, company_id: uuid.UUID):
    role = await roles.resolve_for_company(code, company_id)
    if role is None:
        raise RoleNotFoundError(
            f"No role with code '{code}' in this company", details={"role": code}
        )
    return role


class ListCompanyMembersUseCase:
    def __init__(self, members: CompanyMemberRepository, users: UserRepository) -> None:
        self._members = members
        self._users = users

    async def execute(self, tenant: TenantContext) -> list[CompanyMemberDTO]:
        memberships = await self._members.list_by_company(tenant.company_id)
        result: list[CompanyMemberDTO] = []
        for membership in memberships:
            user = await self._users.get_by_id(membership.user_id)
            if user is None:
                continue
            result.append(
                CompanyMemberDTO(
                    id=membership.id,
                    user_id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    role=membership.role_code,
                    role_id=membership.role_id,
                    is_active=membership.is_active,
                )
            )
        return result


class AddCompanyMemberUseCase:
    """Attach an existing user to the current company.

    Inviting someone who has no account yet needs an invitation flow (email +
    token); a platform admin can create the account from /admin/users instead.
    """

    def __init__(
        self,
        members: CompanyMemberRepository,
        users: UserRepository,
        roles: RoleRepository,
    ) -> None:
        self._members = members
        self._users = users
        self._roles = roles

    async def execute(
        self, command: AddMemberCommand, *, tenant: TenantContext
    ) -> CompanyMemberDTO:
        user = await self._users.get_by_email(str(command.email))
        if user is None:
            raise UserNotFoundError("No account exists for that email address")

        if await self._members.get(tenant.company_id, user.id) is not None:
            raise MembershipAlreadyExistsError()

        role = await _resolve_role(self._roles, command.role, tenant.company_id)

        membership = await self._members.add(
            CompanyMember(
                company_id=tenant.company_id,
                user_id=user.id,
                role_id=role.id,
                role_code=role.code,
            )
        )
        return CompanyMemberDTO(
            id=membership.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=role.code,
            role_id=role.id,
            is_active=membership.is_active,
        )


class ChangeMemberRoleUseCase:
    def __init__(
        self,
        members: CompanyMemberRepository,
        users: UserRepository,
        roles: RoleRepository,
    ) -> None:
        self._members = members
        self._users = users
        self._roles = roles

    async def execute(
        self, user_id: uuid.UUID, command: ChangeMemberRoleCommand, *, tenant: TenantContext
    ) -> CompanyMemberDTO:
        membership = await self._members.get(tenant.company_id, user_id)
        if membership is None:
            raise MembershipNotFoundError("That user is not a member of this company")

        if membership.user_id == tenant.user_id and not tenant.is_platform_admin:
            # Otherwise the last owner can demote themselves and lock the whole
            # company out of its own administration.
            raise BusinessRuleError(
                "You cannot change your own role",
                code="CANNOT_CHANGE_OWN_ROLE",
            )

        role = await _resolve_role(self._roles, command.role, tenant.company_id)
        membership.change_role(role.id, role.code)
        if command.is_active is not None:
            membership.activate() if command.is_active else membership.deactivate()

        updated = await self._members.update(membership)
        user = await self._users.get_by_id(user_id)
        return CompanyMemberDTO(
            id=updated.id,
            user_id=user_id,
            email=user.email if user else "",
            full_name=user.full_name if user else "",
            role=role.code,
            role_id=role.id,
            is_active=updated.is_active,
        )
