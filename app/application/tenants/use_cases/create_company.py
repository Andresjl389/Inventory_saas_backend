import uuid

from app.application.tenants.dto.company import CompanyDTO, CreateCompanyCommand
from app.domain.authorization.permissions import SystemRole
from app.domain.authorization.repositories.role_repository import RoleRepository
from app.domain.tenants.entities.company import Company
from app.domain.tenants.entities.company_member import CompanyMember
from app.domain.tenants.repositories.company_member_repository import CompanyMemberRepository
from app.domain.tenants.repositories.company_repository import CompanyRepository
from app.domain.tenants.repositories.tenant_scope import TenantScope


class CreateCompanyUseCase:
    """Create a tenant. The creator always becomes its OWNER -- otherwise the
    company would exist with nobody able to reach it.

    The id is generated first so the transaction can enter the new tenant's
    scope *before* the INSERT: RLS on `companies` and `company_members` only
    accepts rows belonging to the current company.
    """

    def __init__(
        self,
        companies: CompanyRepository,
        members: CompanyMemberRepository,
        roles: RoleRepository,
        tenant_scope: TenantScope,
    ) -> None:
        self._companies = companies
        self._members = members
        self._roles = roles
        self._tenant_scope = tenant_scope

    async def execute(self, command: CreateCompanyCommand, *, owner_id: uuid.UUID) -> CompanyDTO:
        owner_role = await self._roles.get_by_code(SystemRole.OWNER.value, company_id=None)
        assert owner_role is not None, "the OWNER system role is seeded by migration 0008"

        company = Company(
            name=command.name.strip(),
            legal_name=command.legal_name,
            document_type=command.document_type,
            document_number=command.document_number,
            email=str(command.email) if command.email else None,
            phone=command.phone,
        )
        await self._tenant_scope.enter(company.id)

        created = await self._companies.add(company)
        await self._members.add(
            CompanyMember(
                company_id=created.id,
                user_id=owner_id,
                role_id=owner_role.id,
                role_code=owner_role.code,
            )
        )
        return CompanyDTO.model_validate(created, from_attributes=True)
