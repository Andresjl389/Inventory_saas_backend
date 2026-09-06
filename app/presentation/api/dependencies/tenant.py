"""Tenant resolution.

The client may *propose* a company through the X-Company-ID header; it is only
accepted after the backend confirms an active membership and an operational
company. The resolved context is then pushed into PostgreSQL, where RLS becomes
the last barrier between tenants.
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
from app.presentation.api.dependencies.repositories import CompanyRepoDep, MemberRepoDep
from app.shared.exceptions import ValidationError
from app.shared.logging.context import company_id_var

COMPANY_HEADER = "X-Company-ID"


async def get_tenant_context(
    session: SessionDep,
    user: CurrentUserDep,
    companies: CompanyRepoDep,
    members: MemberRepoDep,
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

    membership = await members.get(company_id, user.id)
    if membership is None or not membership.is_active:
        raise MembershipNotFoundError()

    company = await companies.get_by_id(company_id)
    if company is None:
        raise InvalidCompanyError("Company not found")
    if company.status is not CompanyStatus.ACTIVE:
        raise InvalidCompanyError(f"Company is {company.status.value.lower()}")

    await set_current_company(session, company_id)
    company_id_var.set(str(company_id))

    return TenantContext(company_id=company_id, user_id=user.id, role=membership.role)


TenantDep = Annotated[TenantContext, Depends(get_tenant_context)]


def require_permission(permission: str) -> Callable[[TenantContext], TenantContext]:
    """Route guard: application-layer authorization, one layer above RLS."""

    def guard(tenant: TenantDep) -> TenantContext:
        if not tenant.has_permission(permission):
            raise InsufficientRoleError(
                f"Role {tenant.role.value} cannot perform '{permission}'",
                details={"required_permission": permission, "role": tenant.role.value},
            )
        return tenant

    return guard
