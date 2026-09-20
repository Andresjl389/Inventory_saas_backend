import uuid

from app.application.notifications.dto.notification import (
    ListNotificationsQuery,
    NotificationDTO,
    NotificationPageDTO,
)
from app.domain.notifications.repositories.notification_repository import (
    NotificationRepository,
)
from app.domain.shared.pagination import Page
from app.domain.tenants.tenant_context import TenantContext
from app.shared.exceptions import NotFoundError


class ListNotificationsUseCase:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def execute(
        self, query: ListNotificationsQuery, *, tenant: TenantContext
    ) -> NotificationPageDTO:
        result = await self._notifications.list(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            only_unread=query.only_unread,
        )
        return NotificationPageDTO(
            items=[
                NotificationDTO.model_validate(row, from_attributes=True) for row in result.items
            ],
            total=result.total,
            unread=await self._notifications.count_unread(tenant.company_id),
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class MarkNotificationReadUseCase:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def execute(
        self, notification_id: uuid.UUID, *, tenant: TenantContext
    ) -> NotificationDTO:
        if await self._notifications.get_by_id(tenant.company_id, notification_id) is None:
            raise NotFoundError("Notification not found", code="NOTIFICATION_NOT_FOUND")
        updated = await self._notifications.mark_read(tenant.company_id, notification_id)
        return NotificationDTO.model_validate(updated, from_attributes=True)
