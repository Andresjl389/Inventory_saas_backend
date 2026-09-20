"""Plans and subscriptions.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.domain.billing.entities.plan import SubscriptionStatus
from app.infrastructure.database.migration_helpers import (
    enum_column,
    money_column,
    timestamps,
    uuid_column,
    uuid_pk,
)
from app.infrastructure.database.rls import (
    disable_tenant_rls,
    enable_catalog_rls,
    enable_platform_tenant_rls,
)

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = tuple(status.value for status in SubscriptionStatus)

# Sensible starting catalogue; the platform admin edits it from /admin/plans.
SEED_PLANS = [
    {
        "code": "FREE",
        "name": "Free",
        "description": "For trying the product out",
        "price_monthly": "0",
        "max_users": 2,
        "max_products": 50,
        "max_warehouses": 1,
    },
    {
        "code": "STANDARD",
        "name": "Standard",
        "description": "Shared database, room to grow",
        "price_monthly": "49",
        "max_users": 10,
        "max_products": 5000,
        "max_warehouses": 5,
    },
    {
        "code": "ENTERPRISE",
        "name": "Enterprise",
        "description": "No limits",
        "price_monthly": "199",
        "max_users": 0,
        "max_products": 0,
        "max_warehouses": 0,
    },
]


def upgrade() -> None:
    op.create_table(
        "plans",
        uuid_pk(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        money_column("price_monthly"),
        # 0 means unlimited: a NULL would need special-casing everywhere.
        sa.Column("max_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_products", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_warehouses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_plans"),
        sa.UniqueConstraint("code", name="uq_plans_code"),
        sa.CheckConstraint("max_users >= 0", name="ck_plans_max_users_non_negative"),
        sa.CheckConstraint("max_products >= 0", name="ck_plans_max_products_non_negative"),
        sa.CheckConstraint("max_warehouses >= 0", name="ck_plans_max_warehouses_non_negative"),
    )

    op.bulk_insert(
        sa.table(
            "plans",
            sa.column("code", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
            sa.column("price_monthly", sa.Numeric),
            sa.column("max_users", sa.Integer),
            sa.column("max_products", sa.Integer),
            sa.column("max_warehouses", sa.Integer),
        ),
        SEED_PLANS,
    )

    op.create_table(
        "subscriptions",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("plan_id"),
        enum_column(
            "status", STATUSES, "subscription_status", nullable=False, server_default="TRIALING"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_subscriptions_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name="fk_subscriptions_plan_id_plans", ondelete="RESTRICT"
        ),
        # One live subscription per company keeps "which plan am I on" unambiguous.
        sa.UniqueConstraint("company_id", name="uq_subscriptions_company_id"),
    )
    op.create_index("ix_subscriptions_company_id", "subscriptions", ["company_id"])

    # Seeding happens above, before RLS: the migration has no admin flag set.
    enable_catalog_rls(op, "plans")
    enable_platform_tenant_rls(op, "subscriptions")


def downgrade() -> None:
    disable_tenant_rls(op, "subscriptions")
    disable_tenant_rls(op, "plans")
    op.drop_table("subscriptions")
    op.drop_table("plans")
