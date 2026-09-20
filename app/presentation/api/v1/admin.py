"""Platform administration.

Everything here is gated on `users.is_superuser` -- the column, not a token
claim -- by `PlatformAdminDep`. The same check raised `app.is_platform_admin`
for this transaction, so the API guard and the RLS policies always agree.

These routes never take X-Company-ID: they operate on the platform tables
(companies, users, plans, subscriptions, the audit log). To touch a tenant's
business data an operator uses the normal API with X-Company-ID set, which puts
them on the same single-tenant path as everyone else.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.application.audit.dto.audit import AuditPageDTO, ListAuditQuery
from app.application.audit.use_cases.read_audit_log import ReadAuditLogUseCase
from app.application.platform.dto.admin import (
    AdminCompanyDTO,
    AdminCompanyPageDTO,
    AdminUserDTO,
    AdminUserPageDTO,
    AssignSubscriptionCommand,
    CreatePlanCommand,
    CreateUserCommand,
    ListCompaniesQuery,
    ListUsersQuery,
    PlanDTO,
    PlatformStatsDTO,
    ProvisionCompanyCommand,
    ProvisionedCompanyDTO,
    SubscriptionDTO,
    UpdateCompanyCommand,
    UpdatePlanCommand,
    UpdateUserCommand,
)
from app.application.platform.use_cases.manage_billing import (
    AssignSubscriptionUseCase,
    CreatePlanUseCase,
    GetSubscriptionUseCase,
    ListPlansUseCase,
    UpdatePlanUseCase,
)
from app.application.platform.use_cases.manage_companies import (
    GetCompanyUseCase,
    ListCompaniesUseCase,
    ProvisionCompanyUseCase,
    UpdateCompanyUseCase,
)
from app.application.platform.use_cases.manage_users import (
    CreateUserUseCase,
    ListUsersUseCase,
    UpdateUserUseCase,
)
from app.application.tenants.dto.company import CompanyMemberDTO
from app.application.tenants.use_cases.manage_members import ListCompanyMembersUseCase
from app.domain.audit.entities.audit_entry import AuditAction
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.entities.company import CompanyStatus
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.platform import PlatformAdminDep
from app.presentation.api.dependencies.repositories import (
    AuditRepoDep,
    AuditServiceDep,
    CompanyRepoDep,
    MemberRepoDep,
    PlanRepoDep,
    PlatformStatsDep,
    RoleRepoDep,
    SubscriptionRepoDep,
    UserRepoDep,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@router.get("/stats", response_model=PlatformStatsDTO)
async def platform_stats(admin: PlatformAdminDep, stats: PlatformStatsDep) -> PlatformStatsDTO:
    return PlatformStatsDTO(**await stats.counts())


# --------------------------------------------------------------------------
# Companies
# --------------------------------------------------------------------------
@router.post(
    "/companies", response_model=ProvisionedCompanyDTO, status_code=status.HTTP_201_CREATED
)
async def provision_company(
    command: ProvisionCompanyCommand,
    admin: PlatformAdminDep,
    companies: CompanyRepoDep,
    members: MemberRepoDep,
    users: UserRepoDep,
    roles: RoleRepoDep,
    plans: PlanRepoDep,
    subscriptions: SubscriptionRepoDep,
    audit: AuditServiceDep,
) -> ProvisionedCompanyDTO:
    """Create a company, give it an owner, and put it on a plan.

    If `owner_email` matches an existing account that user becomes the owner;
    otherwise the account is created and `owner_password` is required.
    """
    use_case = ProvisionCompanyUseCase(
        companies, members, users, roles, plans, subscriptions, audit
    )
    return await use_case.execute(command, actor_id=admin.id)


@router.get("/companies", response_model=AdminCompanyPageDTO)
async def list_companies(
    admin: PlatformAdminDep,
    companies: CompanyRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    company_status: Annotated[CompanyStatus | None, Query(alias="status")] = None,
) -> AdminCompanyPageDTO:
    query = ListCompaniesQuery(page=page, size=size, search=search, status=company_status)
    return await ListCompaniesUseCase(companies).execute(query)


@router.get("/companies/{company_id}", response_model=AdminCompanyDTO)
async def get_company(
    company_id: uuid.UUID, admin: PlatformAdminDep, companies: CompanyRepoDep
) -> AdminCompanyDTO:
    return await GetCompanyUseCase(companies).execute(company_id)


@router.patch("/companies/{company_id}", response_model=AdminCompanyDTO)
async def update_company(
    company_id: uuid.UUID,
    command: UpdateCompanyCommand,
    admin: PlatformAdminDep,
    companies: CompanyRepoDep,
    audit: AuditServiceDep,
) -> AdminCompanyDTO:
    """Also how a company is suspended or reactivated: send `status`.

    A SUSPENDED company stops accepting requests from its own members on the
    next request -- the tenant dependency checks the status every time.
    """
    return await UpdateCompanyUseCase(companies, audit).execute(
        company_id, command, actor_id=admin.id
    )


@router.get("/companies/{company_id}/members", response_model=list[CompanyMemberDTO])
async def list_company_members(
    company_id: uuid.UUID,
    admin: PlatformAdminDep,
    members: MemberRepoDep,
    users: UserRepoDep,
) -> list[CompanyMemberDTO]:
    # A synthetic context: the admin is not a member, and the platform policy
    # on company_members is what makes the read possible.
    context = TenantContext.for_platform_admin(company_id=company_id, user_id=admin.id)
    return await ListCompanyMembersUseCase(members, users).execute(context)


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
@router.get("/users", response_model=AdminUserPageDTO)
async def list_users(
    admin: PlatformAdminDep,
    users: UserRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
    is_superuser: bool | None = None,
) -> AdminUserPageDTO:
    query = ListUsersQuery(
        page=page, size=size, search=search, is_active=is_active, is_superuser=is_superuser
    )
    return await ListUsersUseCase(users).execute(query)


@router.post("/users", response_model=AdminUserDTO, status_code=status.HTTP_201_CREATED)
async def create_user(
    command: CreateUserCommand,
    admin: PlatformAdminDep,
    users: UserRepoDep,
    audit: AuditServiceDep,
) -> AdminUserDTO:
    return await CreateUserUseCase(users, audit).execute(command, actor_id=admin.id)


@router.patch("/users/{user_id}", response_model=AdminUserDTO)
async def update_user(
    user_id: uuid.UUID,
    command: UpdateUserCommand,
    admin: PlatformAdminDep,
    users: UserRepoDep,
    audit: AuditServiceDep,
) -> AdminUserDTO:
    """Reset a password, deactivate an account, or grant platform-admin rights."""
    return await UpdateUserUseCase(users, audit).execute(user_id, command, actor_id=admin.id)


# --------------------------------------------------------------------------
# Plans and subscriptions
# --------------------------------------------------------------------------
@router.get("/plans", response_model=list[PlanDTO])
async def list_plans(
    admin: PlatformAdminDep, plans: PlanRepoDep, is_active: bool | None = None
) -> list[PlanDTO]:
    return await ListPlansUseCase(plans).execute(is_active=is_active)


@router.post("/plans", response_model=PlanDTO, status_code=status.HTTP_201_CREATED)
async def create_plan(
    command: CreatePlanCommand, admin: PlatformAdminDep, plans: PlanRepoDep
) -> PlanDTO:
    return await CreatePlanUseCase(plans).execute(command)


@router.patch("/plans/{plan_id}", response_model=PlanDTO)
async def update_plan(
    plan_id: uuid.UUID,
    command: UpdatePlanCommand,
    admin: PlatformAdminDep,
    plans: PlanRepoDep,
) -> PlanDTO:
    return await UpdatePlanUseCase(plans).execute(plan_id, command)


@router.get("/companies/{company_id}/subscription", response_model=SubscriptionDTO | None)
async def get_subscription(
    company_id: uuid.UUID,
    admin: PlatformAdminDep,
    subscriptions: SubscriptionRepoDep,
    plans: PlanRepoDep,
) -> SubscriptionDTO | None:
    return await GetSubscriptionUseCase(subscriptions, plans).execute(company_id)


@router.put("/companies/{company_id}/subscription", response_model=SubscriptionDTO)
async def assign_subscription(
    company_id: uuid.UUID,
    command: AssignSubscriptionCommand,
    admin: PlatformAdminDep,
    companies: CompanyRepoDep,
    plans: PlanRepoDep,
    subscriptions: SubscriptionRepoDep,
    audit: AuditServiceDep,
) -> SubscriptionDTO:
    use_case = AssignSubscriptionUseCase(companies, plans, subscriptions, audit)
    return await use_case.execute(company_id, command, actor_id=admin.id)


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------
@router.get("/audit", response_model=AuditPageDTO)
async def platform_audit_log(
    admin: PlatformAdminDep,
    audit: AuditRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    action: AuditAction | None = None,
    company_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> AuditPageDTO:
    """Every audited event, across tenants. Pass `company_id` to narrow it."""
    query = ListAuditQuery(
        page=page, size=size, action=action, company_id=company_id, actor_user_id=actor_user_id
    )
    return await ReadAuditLogUseCase(audit).execute(query, tenant=None)
