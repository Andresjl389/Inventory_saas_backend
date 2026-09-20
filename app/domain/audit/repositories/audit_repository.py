import uuid
from typing import Protocol

from app.domain.audit.entities.audit_entry import AuditAction, AuditEntry
from app.domain.shared.pagination import Page, PaginatedResult


class AuditRepository(Protocol):
    async def add(self, entry: AuditEntry) -> AuditEntry: ...

    async def list(
        self,
        *,
        page: Page,
        company_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        action: AuditAction | None = None,
    ) -> PaginatedResult[AuditEntry]: ...
