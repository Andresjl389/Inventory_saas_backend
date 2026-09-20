"""Audit log, billing and notifications."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.audit.entities.audit_entry import AuditAction
from app.domain.billing.entities.plan import SubscriptionStatus
from app.domain.notifications.entities.notification import NotificationType
from app.infrastructure.database.base import (
    MONEY,
    QUANTITY,
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)


class AuditLogModel(UUIDPrimaryKeyMixin, Base):
    """Append-only. company_id is NULL for platform-level actions."""

    __tablename__ = "audit_logs"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[AuditAction] = mapped_column(
        enum_column(AuditAction, "audit_action"), nullable=False
    )
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_audit_logs_company_id", "company_id"),
        Index("ix_audit_logs_company_id_created_at", "company_id", "created_at"),
        Index("ix_audit_logs_actor_user_id", "actor_user_id"),
        Index("ix_audit_logs_action", "action"),
    )


class PlanModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Global catalogue: no company_id, managed only by platform admins."""

    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_monthly: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    # 0 == unlimited.
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_products: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_warehouses: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )


class SubscriptionModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_column(SubscriptionStatus, "subscription_status"),
        nullable=False,
        default=SubscriptionStatus.TRIALING,
        server_default=SubscriptionStatus.TRIALING.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # One live subscription per company keeps "which plan am I on?" unambiguous.
    __table_args__ = (UniqueConstraint("company_id"),)


class NotificationModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "notifications"

    type: Mapped[NotificationType] = mapped_column(
        enum_column(NotificationType, "notification_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_notifications_company_id_created_at", "company_id", "created_at"),
        Index("ix_notifications_company_id_is_read", "company_id", "is_read"),
        # A repeat low-stock sweep must not pile up duplicates for a product
        # that is still below its threshold, so the key is unique while unread.
        Index(
            "uq_notifications_company_id_dedupe_key_unread",
            "company_id",
            "dedupe_key",
            unique=True,
            postgresql_where="dedupe_key IS NOT NULL AND is_read = false",
        ),
    )


# Re-exported so the products model can reuse the quantity type.
__all__ = [
    "AuditLogModel",
    "NotificationModel",
    "PlanModel",
    "QUANTITY",
    "SubscriptionModel",
]
