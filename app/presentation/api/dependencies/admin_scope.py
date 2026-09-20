"""Letting an operator work inside one company from an admin route.

The business tables have no platform-admin escape in their RLS policies, by
design: there is no request that reads two tenants' data at once. So an admin
endpoint that needs a company's products or sales *enters* that company first,
exactly as a member's request does, and everything below sees a normal
single-tenant context.

The company id comes from the path here rather than from X-Company-ID, which
keeps `/admin/companies/{id}/...` readable as what it is.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Path

from app.domain.tenants.exceptions import CompanyNotFoundError
from app.domain.tenants.tenant_context import TenantContext
from app.infrastructure.database.tenant_context import set_current_company
from app.presentation.api.dependencies.database import SessionDep
from app.presentation.api.dependencies.platform import PlatformAdminDep
from app.presentation.api.dependencies.repositories import CompanyRepoDep
from app.shared.logging.context import company_id_var


async def get_admin_company_scope(
    session: SessionDep,
    admin: PlatformAdminDep,
    companies: CompanyRepoDep,
    company_id: Annotated[uuid.UUID, Path(description="Company to act on")],
) -> TenantContext:
    # Readable thanks to the platform policy on `companies`; a suspended one is
    # fine, since inspecting it is often the reason for being here.
    if await companies.get_by_id(company_id) is None:
        raise CompanyNotFoundError()

    await set_current_company(session, company_id)
    company_id_var.set(str(company_id))
    return TenantContext.for_platform_admin(company_id=company_id, user_id=admin.id)


AdminCompanyScopeDep = Annotated[TenantContext, Depends(get_admin_company_scope)]
