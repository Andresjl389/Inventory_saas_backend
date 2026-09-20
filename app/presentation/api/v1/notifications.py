import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.notifications.dto.notification import (
    ListNotificationsQuery,
    NotificationDTO,
    NotificationPageDTO,
)
from app.application.notifications.use_cases.notification_use_cases import (
    ListNotificationsUseCase,
    MarkNotificationReadUseCase,
)
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import NotificationRepoDep
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Any member of the company may read their company's notifications.
ReadDep = Annotated[TenantContext, Depends(require_permission("company.read"))]


@router.get("", response_model=NotificationPageDTO)
async def list_notifications(
    tenant: ReadDep,
    notifications: NotificationRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    only_unread: bool = False,
) -> NotificationPageDTO:
    query = ListNotificationsQuery(page=page, size=size, only_unread=only_unread)
    return await ListNotificationsUseCase(notifications).execute(query, tenant=tenant)


@router.post("/{notification_id}/read", response_model=NotificationDTO)
async def mark_read(
    notification_id: uuid.UUID, tenant: ReadDep, notifications: NotificationRepoDep
) -> NotificationDTO:
    return await MarkNotificationReadUseCase(notifications).execute(notification_id, tenant=tenant)
