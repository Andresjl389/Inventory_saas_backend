import uuid

from app.application.tenants.dto.company import CompanyDTO, CreateCompanyCommand
from app.domain.tenants.entities.company import Company
from app.domain.tenants.entities.company_member import CompanyMember, CompanyRole
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
        tenant_scope: TenantScope,
    ) -> None:
        self._companies = companies
        self._members = members
        self._tenant_scope = tenant_scope

    async def execute(self, command: CreateCompanyCommand, *, owner_id: uuid.UUID) -> CompanyDTO:
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
            CompanyMember(company_id=created.id, user_id=owner_id, role=CompanyRole.OWNER)
        )
        return CompanyDTO.model_validate(created, from_attributes=True)
