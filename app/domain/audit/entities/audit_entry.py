"""Audit trail.

One row per state change worth explaining later: who did what, to which record,
and with what payload. `company_id` is nullable because platform-level actions
(creating a company, changing a plan) belong to no tenant.
"""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.shared.entities import BaseEntity


class AuditAction(StrEnum):
    COMPANY_CREATED = "COMPANY_CREATED"
    COMPANY_UPDATED = "COMPANY_UPDATED"
    COMPANY_SUSPENDED = "COMPANY_SUSPENDED"
    COMPANY_ACTIVATED = "COMPANY_ACTIVATED"
    MEMBER_ADDED = "MEMBER_ADDED"
    MEMBER_ROLE_CHANGED = "MEMBER_ROLE_CHANGED"
    MEMBER_DEACTIVATED = "MEMBER_DEACTIVATED"
    ROLE_CREATED = "ROLE_CREATED"
    ROLE_UPDATED = "ROLE_UPDATED"
    ROLE_DELETED = "ROLE_DELETED"
    USER_CREATED = "USER_CREATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_PASSWORD_RESET = "USER_PASSWORD_RESET"
    SUBSCRIPTION_CHANGED = "SUBSCRIPTION_CHANGED"
    STOCK_ADJUSTED = "STOCK_ADJUSTED"
    STOCK_TRANSFERRED = "STOCK_TRANSFERRED"
    SALE_COMPLETED = "SALE_COMPLETED"
    SALE_CANCELLED = "SALE_CANCELLED"
    SALE_REFUNDED = "SALE_REFUNDED"
    PURCHASE_COMPLETED = "PURCHASE_COMPLETED"
    PURCHASE_CANCELLED = "PURCHASE_CANCELLED"


@dataclass(kw_only=True)
class AuditEntry(BaseEntity):
    action: AuditAction
    company_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    # Never put secrets here: the payload is readable by anyone with audit.read.
    payload: dict[str, Any] = field(default_factory=dict)
    ip_address: str | None = None
