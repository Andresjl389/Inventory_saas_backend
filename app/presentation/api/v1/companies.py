from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.application.tenants.dto.company import (
    AddMemberCommand,
    CompanyDTO,
    CompanyMemberDTO,
    CreateCompanyCommand,
    MembershipDTO,
)
from app.application.tenants.use_cases.create_company import CreateCompanyUseCase
from app.application.tenants.use_cases.list_my_companies import ListMyCompaniesUseCase
from app.application.tenants.use_cases.manage_members import (
    AddCompanyMemberUseCase,
    ListCompanyMembersUseCase,
)
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.auth import CurrentUserDep
from app.presentation.api.dependencies.repositories import (
    CompanyRepoDep,
    MemberRepoDep,
    TenantScopeDep,
    UserRepoDep,
)
from app.presentation.api.dependencies.tenant import TenantDep, require_permission

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[MembershipDTO])
async def list_my_companies(
    user: CurrentUserDep,
    companies: CompanyRepoDep,
    members: MemberRepoDep,
) -> list[MembershipDTO]:
    """Companies the caller belongs to -- the source for the company switcher.

    No X-Company-ID needed: this endpoint runs before a tenant is chosen.
    """
    return await ListMyCompaniesUseCase(companies, members).execute(user.id)


@router.post("", response_model=CompanyDTO, status_code=status.HTTP_201_CREATED)
async def create_company(
    command: CreateCompanyCommand,
    user: CurrentUserDep,
    companies: CompanyRepoDep,
    members: MemberRepoDep,
    tenant_scope: TenantScopeDep,
) -> CompanyDTO:
    return await CreateCompanyUseCase(companies, members, tenant_scope).execute(
        command, owner_id=user.id
    )


@router.get("/current", response_model=CompanyDTO)
async def get_current_company(tenant: TenantDep, companies: CompanyRepoDep) -> CompanyDTO:
    company = await companies.get_by_id(tenant.company_id)
    assert company is not None  # the tenant dependency already validated it
    return CompanyDTO.model_validate(company, from_attributes=True)


@router.get("/current/members", response_model=list[CompanyMemberDTO])
async def list_members(
    tenant: Annotated[TenantContext, Depends(require_permission("members.read"))],
    members: MemberRepoDep,
    users: UserRepoDep,
) -> list[CompanyMemberDTO]:
    return await ListCompanyMembersUseCase(members, users).execute(tenant)


@router.post(
    "/current/members", response_model=CompanyMemberDTO, status_code=status.HTTP_201_CREATED
)
async def add_member(
    command: AddMemberCommand,
    tenant: Annotated[TenantContext, Depends(require_permission("members.manage"))],
    members: MemberRepoDep,
    users: UserRepoDep,
) -> CompanyMemberDTO:
    return await AddCompanyMemberUseCase(members, users).execute(command, tenant=tenant)
