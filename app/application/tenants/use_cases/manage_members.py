import uuid

from app.application.tenants.dto.company import (
    AddMemberCommand,
    ChangeMemberRoleCommand,
    CompanyMemberDTO,
)
from app.domain.authorization.exceptions import RoleNotFoundError
from app.domain.authorization.repositories.role_repository import RoleRepository
from app.domain.identity.entities.user import User
from app.domain.identity.exceptions import UserNotFoundError
from app.domain.identity.repositories.user_repository import UserRepository
from app.domain.identity.value_objects.email import Email
from app.domain.tenants.entities.company_member import CompanyMember
from app.domain.tenants.exceptions import (
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
)
from app.domain.tenants.repositories.company_member_repository import CompanyMemberRepository
from app.domain.tenants.tenant_context import TenantContext
from app.shared.exceptions import BusinessRuleError, ValidationError
from app.shared.security import hash_password


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
    """Attach a person to a company that already exists.

    The company is always identified by id (it comes from the tenant context,
    or from the path on the platform-admin route) -- never created here, and
    never conjured from a name.

    There is no email invitation yet, so onboarding somebody new means the
    administrator sets their first password and hands it over. Worth knowing:
    nothing verifies the address belongs to that person.
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
        email = Email(command.email).value
        user = await self._users.get_by_email(email)

        if user is None:
            user = await self._create_account(command, email)

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

    async def _create_account(self, command: AddMemberCommand, email: str):
        if not command.password:
            raise UserNotFoundError(
                "No account exists for that email address. Send a password "
                "(and optionally a name) to create it.",
                code="ACCOUNT_DETAILS_REQUIRED",
            )
        if not command.first_name:
            raise ValidationError(
                "first_name is required when creating the account",
                code="ACCOUNT_DETAILS_REQUIRED",
            )

        return await self._users.add(
            User(
                email=email,
                password_hash=hash_password(command.password),
                first_name=command.first_name.strip(),
                last_name=(command.last_name or "").strip(),
            )
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
