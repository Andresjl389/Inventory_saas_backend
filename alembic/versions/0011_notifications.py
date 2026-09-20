"""Notifications and the reorder threshold the low-stock job watches.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.domain.notifications.entities.notification import NotificationType
from app.infrastructure.database.migration_helpers import (
    enum_column,
    quantity_column,
    timestamps,
    uuid_column,
    uuid_pk,
)
from app.infrastructure.database.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPES = tuple(item.value for item in NotificationType)


def upgrade() -> None:
    op.add_column(
        "products",
        quantity_column("min_stock", default="0"),
    )
    op.create_check_constraint("ck_products_min_stock_non_negative", "products", "min_stock >= 0")

    op.create_table(
        "notifications",
        uuid_pk(),
        uuid_column("company_id"),
        enum_column("type", TYPES, "notification_type", nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dedupe_key", sa.String(200), nullable=True),
        uuid_column("entity_id", nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_notifications_company_id_companies",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_notifications_company_id", "notifications", ["company_id"])
    op.create_index(
        "ix_notifications_company_id_created_at", "notifications", ["company_id", "created_at"]
    )
    op.create_index(
        "ix_notifications_company_id_is_read", "notifications", ["company_id", "is_read"]
    )
    # A repeat low-stock sweep must not pile up duplicates for a product that
    # is still below its threshold, so the key is unique while the row is unread.
    op.create_index(
        "uq_notifications_company_id_dedupe_key_unread",
        "notifications",
        ["company_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL AND is_read = false"),
    )

    enable_tenant_rls(op, "notifications")


def downgrade() -> None:
    disable_tenant_rls(op, "notifications")
    op.drop_table("notifications")
    op.drop_constraint("ck_products_min_stock_non_negative", "products", type_="check")
    op.drop_column("products", "min_stock")
