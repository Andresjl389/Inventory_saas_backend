"""Tenant resolution.

The client may *propose* a company through the X-Company-ID header; it is only
accepted after the backend confirms an active membership and an operational
company. The resolved context is then pushed into PostgreSQL, where RLS becomes
the last barrier between tenants.

A platform administrator is the one exception: they hold no membership, so they
step into a company directly. They still get a single-company context -- there
is no request that reads two tenants' business data at once.
"""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header

from app.domain.tenants.entities.company import CompanyStatus
from app.domain.tenants.exceptions import (
    InsufficientRoleError,
    InvalidCompanyError,
    MembershipNotFoundError,
)
from app.domain.tenants.tenant_context import TenantContext
from app.infrastructure.database.tenant_context import set_current_company
from app.presentation.api.dependencies.auth import CurrentUserDep
from app.presentation.api.dependencies.database import SessionDep
from app.presentation.api.dependencies.repositories import (
    CompanyRepoDep,
    MemberRepoDep,
    RoleRepoDep,
)
from app.shared.exceptions import ValidationError
from app.shared.logging.context import company_id_var

COMPANY_HEADER = "X-Company-ID"


async def get_tenant_context(
    session: SessionDep,
    user: CurrentUserDep,
    companies: CompanyRepoDep,
    members: MemberRepoDep,
    roles: RoleRepoDep,
    x_company_id: Annotated[
        str | None,
        Header(alias=COMPANY_HEADER, description="Active company for this request"),
    ] = None,
) -> TenantContext:
    if not x_company_id:
        raise ValidationError(
            f"{COMPANY_HEADER} header is required for this endpoint",
            code="COMPANY_REQUIRED",
        )

    try:
        company_id = uuid.UUID(x_company_id)
    except ValueError as exc:
        raise ValidationError(f"{COMPANY_HEADER} is not a valid UUID") from exc

    company = await companies.get_by_id(company_id)

    if user.is_superuser:
        # Operators must be able to work on a suspended company -- that is
        # often exactly why they are looking at it -- so the status gate below
        # does not apply to them.
        if company is None:
            raise InvalidCompanyError("Company not found")
        await set_current_company(session, company_id)
        company_id_var.set(str(company_id))
        return TenantContext.for_platform_admin(company_id=company_id, user_id=user.id)

    membership = await members.get(company_id, user.id)
    if membership is None or not membership.is_active:
        raise MembershipNotFoundError()

    if company is None:
        raise InvalidCompanyError("Company not found")
    if company.status is not CompanyStatus.ACTIVE:
        raise InvalidCompanyError(f"Company is {company.status.value.lower()}")

    await set_current_company(session, company_id)
    company_id_var.set(str(company_id))

    # Loaded after the company scope is set: role_permissions is itself behind
    # RLS, and the policy needs to know which company we are in.
    permissions = await roles.permissions_of(membership.role_id)

    return TenantContext(
        company_id=company_id,
        user_id=user.id,
        role_code=membership.role_code,
        permissions=permissions,
        role_id=membership.role_id,
    )


TenantDep = Annotated[TenantContext, Depends(get_tenant_context)]


def require_permission(permission: str) -> Callable[[TenantContext], TenantContext]:
    """Route guard: application-layer authorization, one layer above RLS."""

    def guard(tenant: TenantDep) -> TenantContext:
        if not tenant.has_permission(permission):
            raise InsufficientRoleError(
                f"Role {tenant.role_code} cannot perform '{permission}'",
                details={"required_permission": permission, "role": tenant.role_code},
            )
        return tenant

    return guard
