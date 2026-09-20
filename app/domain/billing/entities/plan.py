"""Subscription plans and the subscription a company holds.

Plans are a global catalogue owned by the platform admin; a company never edits
them. The quota fields are enforced by the application layer when a tenant
tries to add the resource in question.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.shared.entities import BaseEntity


class SubscriptionStatus(StrEnum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELLED = "CANCELLED"


UNLIMITED = 0


@dataclass(kw_only=True)
class Plan(BaseEntity):
    code: str
    name: str
    description: str | None = None
    price_monthly: Decimal = Decimal("0")
    # 0 means unlimited -- a NULL would have to be special-cased in every
    # comparison, and "no limit" is a real value, not a missing one.
    max_users: int = UNLIMITED
    max_products: int = UNLIMITED
    max_warehouses: int = UNLIMITED
    is_active: bool = True

    def __post_init__(self) -> None:
        self.code = self.code.strip().upper().replace(" ", "_")

    def allows(self, current: int, limit: int) -> bool:
        return limit == UNLIMITED or current < limit


@dataclass(kw_only=True)
class Subscription(BaseEntity):
    company_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus = SubscriptionStatus.TRIALING
    started_at: datetime | None = None
    current_period_end: datetime | None = None
    cancelled_at: datetime | None = None

    @property
    def is_usable(self) -> bool:
        return self.status in (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE)
