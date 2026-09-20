import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.notifications.entities.notification import NotificationType
from app.domain.shared.pagination import MAX_PAGE_SIZE


class ListNotificationsQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    only_unread: bool = False


class NotificationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    payload: dict[str, Any]
    is_read: bool
    entity_id: uuid.UUID | None
    created_at: datetime


class NotificationPageDTO(BaseModel):
    items: list[NotificationDTO]
    total: int
    unread: int
    page: int
    size: int
    pages: int
