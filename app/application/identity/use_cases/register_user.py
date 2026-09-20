import uuid

from app.application.identity.dto.auth import RegisterUserCommand, UserDTO
from app.domain.authorization.permissions import SystemRole
from app.domain.authorization.repositories.role_repository import RoleRepository
from app.domain.identity.entities.user import User
from app.domain.identity.exceptions import EmailAlreadyRegisteredError
from app.domain.identity.repositories.user_repository import UserRepository
from app.domain.identity.value_objects.email import Email
from app.domain.tenants.entities.company import Company
from app.domain.tenants.entities.company_member import CompanyMember
from app.domain.tenants.repositories.company_member_repository import CompanyMemberRepository
from app.domain.tenants.repositories.company_repository import CompanyRepository
from app.domain.tenants.repositories.tenant_scope import TenantScope
from app.shared.security import hash_password


class RegisterUserUseCase:
    """Sign up a user and, optionally, bootstrap their first company.

    Every write shares the request transaction, so a failure creating the
    membership rolls the user and the company back too.
    """

    def __init__(
        self,
        users: UserRepository,
        companies: CompanyRepository,
        members: CompanyMemberRepository,
        roles: RoleRepository,
        tenant_scope: TenantScope,
    ) -> None:
        self._users = users
        self._companies = companies
        self._members = members
        self._roles = roles
        self._tenant_scope = tenant_scope

    async def execute(self, command: RegisterUserCommand) -> tuple[UserDTO, uuid.UUID | None]:
        email = Email(command.email).value

        if await self._users.exists_by_email(email):
            raise EmailAlreadyRegisteredError()

        user = await self._users.add(
            User(
                email=email,
                password_hash=hash_password(command.password),
                first_name=command.first_name.strip(),
                last_name=command.last_name.strip(),
            )
        )

        company_id: uuid.UUID | None = None
        if command.company_name:
            owner_role = await self._roles.get_by_code(SystemRole.OWNER.value, company_id=None)
            assert owner_role is not None, "the OWNER system role is seeded by migration 0008"

            company = Company(name=command.company_name.strip())
            await self._tenant_scope.enter(company.id)
            created = await self._companies.add(company)
            await self._members.add(
                CompanyMember(
                    company_id=created.id,
                    user_id=user.id,
                    role_id=owner_role.id,
                    role_code=owner_role.code,
                )
            )
            company_id = created.id

        return UserDTO.model_validate(user, from_attributes=True), company_id
