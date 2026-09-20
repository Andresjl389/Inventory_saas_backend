from app.application.audit.dto.audit import AuditEntryDTO, AuditPageDTO, ListAuditQuery
from app.domain.audit.repositories.audit_repository import AuditRepository
from app.domain.shared.pagination import Page
from app.domain.tenants.tenant_context import TenantContext


class ReadAuditLogUseCase:
    """Inside a company, the RLS policy already limits rows to that tenant; the
    company filter here is for the platform admin's cross-tenant view."""

    def __init__(self, audit: AuditRepository) -> None:
        self._audit = audit

    async def execute(
        self, query: ListAuditQuery, *, tenant: TenantContext | None = None
    ) -> AuditPageDTO:
        result = await self._audit.list(
            page=Page(number=query.page, size=query.size),
            company_id=tenant.company_id if tenant else query.company_id,
            actor_user_id=query.actor_user_id,
            action=query.action,
        )
        return AuditPageDTO(
            items=[AuditEntryDTO.model_validate(row, from_attributes=True) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )
