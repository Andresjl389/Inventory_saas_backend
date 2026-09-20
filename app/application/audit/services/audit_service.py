"""Writes the audit trail.

Called from the use cases that change something worth explaining later. It
shares the request transaction, so an action and its audit row commit together:
there is no "it happened but was not logged" and no "logged but rolled back".
"""

import uuid
from typing import Any

from app.domain.audit.entities.audit_entry import AuditAction, AuditEntry
from app.domain.audit.repositories.audit_repository import AuditRepository

# Never copied into an audit payload, whatever the caller passes.
REDACTED_KEYS = frozenset(
    {"password", "password_hash", "access_token", "refresh_token", "authorization", "secret"}
)


def _scrub(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: ("***" if key.lower() in REDACTED_KEYS else value) for key, value in payload.items()
    }


class AuditService:
    def __init__(self, audit: AuditRepository) -> None:
        self._audit = audit

    async def record(
        self,
        action: AuditAction,
        *,
        actor_user_id: uuid.UUID | None = None,
        company_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditEntry:
        return await self._audit.add(
            AuditEntry(
                action=action,
                actor_user_id=actor_user_id,
                company_id=company_id,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=_scrub(payload or {}),
                ip_address=ip_address,
            )
        )
