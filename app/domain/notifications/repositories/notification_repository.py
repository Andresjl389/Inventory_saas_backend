import uuid
from typing import Protocol

from app.domain.notifications.entities.notification import Notification
from app.domain.shared.pagination import Page, PaginatedResult


class NotificationRepository(Protocol):
    async def get_by_id(
        self, company_id: uuid.UUID, notification_id: uuid.UUID
    ) -> Notification | None: ...

    async def list(
        self, company_id: uuid.UUID, *, page: Page, only_unread: bool = False
    ) -> PaginatedResult[Notification]: ...

    async def add_if_absent(self, notification: Notification) -> Notification | None:
        """Insert unless an unread row with the same dedupe_key already exists.

        Returns None when nothing was inserted.
        """
        ...

    async def mark_read(
        self, company_id: uuid.UUID, notification_id: uuid.UUID
    ) -> Notification: ...

    async def count_unread(self, company_id: uuid.UUID) -> int: ...
