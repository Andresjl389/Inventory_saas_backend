from app.application.tenants.dto.company import AddMemberCommand, CompanyMemberDTO
from app.domain.identity.exceptions import UserNotFoundError
from app.domain.identity.repositories.user_repository import UserRepository
from app.domain.tenants.entities.company_member import CompanyMember
from app.domain.tenants.exceptions import MembershipAlreadyExistsError
from app.domain.tenants.repositories.company_member_repository import CompanyMemberRepository
from app.domain.tenants.tenant_context import TenantContext


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
                    role=membership.role,
                    is_active=membership.is_active,
                )
            )
        return result


class AddCompanyMemberUseCase:
    """Attach an existing user to the current company.

    Inviting someone who has no account yet needs an invitation flow (email +
    token); that is deliberately out of scope for this first prototype.
    """

    def __init__(self, members: CompanyMemberRepository, users: UserRepository) -> None:
        self._members = members
        self._users = users

    async def execute(
        self, command: AddMemberCommand, *, tenant: TenantContext
    ) -> CompanyMemberDTO:
        user = await self._users.get_by_email(str(command.email))
        if user is None:
            raise UserNotFoundError("No account exists for that email address")

        if await self._members.get(tenant.company_id, user.id) is not None:
            raise MembershipAlreadyExistsError()

        membership = await self._members.add(
            CompanyMember(company_id=tenant.company_id, user_id=user.id, role=command.role)
        )
        return CompanyMemberDTO(
            id=membership.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            is_active=membership.is_active,
        )
