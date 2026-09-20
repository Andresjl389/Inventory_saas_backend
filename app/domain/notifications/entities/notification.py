"""In-app notifications.

Written by background jobs (low stock sweeps) and by use cases that need to
tell a company something. Delivery channels -- email, webhooks -- read from the
same rows, which is why the body is stored rather than rendered on the fly.
"""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.shared.entities import TenantEntity


class NotificationType(StrEnum):
    LOW_STOCK = "LOW_STOCK"
    SUBSCRIPTION = "SUBSCRIPTION"
    REPORT_READY = "REPORT_READY"
    SYSTEM = "SYSTEM"


@dataclass(kw_only=True)
class Notification(TenantEntity):
    type: NotificationType
    title: str
    body: str
    payload: dict[str, Any] = field(default_factory=dict)
    is_read: bool = False
    # Set for notifications that dedupe: a second low-stock sweep must not
    # create a duplicate row for a product that is still below its threshold.
    dedupe_key: str | None = None
    entity_id: uuid.UUID | None = None

    def mark_read(self) -> None:
        self.is_read = True
        self.touch()
