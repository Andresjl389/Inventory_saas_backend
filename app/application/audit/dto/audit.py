import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.audit.entities.audit_entry import AuditAction
from app.domain.shared.pagination import MAX_PAGE_SIZE


class ListAuditQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    action: AuditAction | None = None
    actor_user_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


class AuditEntryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: AuditAction
    company_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    payload: dict[str, Any]
    ip_address: str | None
    created_at: datetime


class AuditPageDTO(BaseModel):
    items: list[AuditEntryDTO]
    total: int
    page: int
    size: int
    pages: int
