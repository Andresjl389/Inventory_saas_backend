import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.application.tenants.dto.company import (
    AddMemberCommand,
    ChangeMemberRoleCommand,
    CompanyDTO,
    CompanyMemberDTO,
    MembershipDTO,
)
from app.application.tenants.use_cases.list_my_companies import ListMyCompaniesUseCase
from app.application.tenants.use_cases.manage_members import (
    AddCompanyMemberUseCase,
    ChangeMemberRoleUseCase,
    ListCompanyMembersUseCase,
)
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.auth import CurrentUserDep
from app.presentation.api.dependencies.repositories import (
    CompanyRepoDep,
    MemberRepoDep,
    RoleRepoDep,
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

    No X-Company-ID needed: this endpoint runs before a tenant is chosen. An
    account that belongs to nowhere gets an empty list, which is the signal to
    show "you are not a member of any company yet".
    """
    return await ListMyCompaniesUseCase(companies, members).execute(user.id)


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
    roles: RoleRepoDep,
) -> CompanyMemberDTO:
    """`role` is a role *code*: a built-in one or a custom role of this company."""
    return await AddCompanyMemberUseCase(members, users, roles).execute(command, tenant=tenant)


@router.patch("/current/members/{user_id}", response_model=CompanyMemberDTO)
async def change_member_role(
    user_id: uuid.UUID,
    command: ChangeMemberRoleCommand,
    tenant: Annotated[TenantContext, Depends(require_permission("members.manage"))],
    members: MemberRepoDep,
    users: UserRepoDep,
    roles: RoleRepoDep,
) -> CompanyMemberDTO:
    """Change a member's role, or activate/deactivate them."""
    return await ChangeMemberRoleUseCase(members, users, roles).execute(
        user_id, command, tenant=tenant
    )
