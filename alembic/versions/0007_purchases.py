"""Purchases and purchase items.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.infrastructure.database.migration_helpers import (
    enum_column,
    money_column,
    quantity_column,
    timestamps,
    uuid_column,
    uuid_pk,
)
from app.infrastructure.database.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PURCHASE_STATUSES = ("DRAFT", "COMPLETED", "CANCELLED")


def upgrade() -> None:
    op.create_table(
        "purchases",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("supplier_id", nullable=True),
        uuid_column("warehouse_id"),
        enum_column(
            "status", PURCHASE_STATUSES, "purchase_status", nullable=False, server_default="DRAFT"
        ),
        money_column("subtotal"),
        money_column("discount"),
        money_column("tax"),
        money_column("total"),
        sa.Column("notes", sa.Text(), nullable=True),
        uuid_column("created_by", nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_purchases"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_purchases_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_purchases_supplier_id_suppliers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_purchases_warehouse_id_warehouses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_purchases_created_by_users", ondelete="SET NULL"
        ),
        sa.CheckConstraint("total >= 0", name="ck_purchases_total_non_negative"),
    )
    op.create_index("ix_purchases_company_id", "purchases", ["company_id"])
    op.create_index("ix_purchases_company_id_created_at", "purchases", ["company_id", "created_at"])
    op.create_index("ix_purchases_company_id_status", "purchases", ["company_id", "status"])
    op.create_index(
        "ix_purchases_company_id_supplier_id", "purchases", ["company_id", "supplier_id"]
    )

    op.create_table(
        "purchase_items",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("purchase_id"),
        uuid_column("product_id"),
        quantity_column("quantity"),
        money_column("unit_cost", default=None),
        money_column("discount"),
        money_column("tax"),
        money_column("total"),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_items"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_purchase_items_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_id"],
            ["purchases.id"],
            name="fk_purchase_items_purchase_id_purchases",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_purchase_items_product_id_products",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_items_quantity_positive"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_purchase_items_unit_cost_non_negative"),
        sa.CheckConstraint("total >= 0", name="ck_purchase_items_total_non_negative"),
    )
    op.create_index("ix_purchase_items_company_id", "purchase_items", ["company_id"])
    op.create_index("ix_purchase_items_purchase_id", "purchase_items", ["purchase_id"])
    op.create_index(
        "ix_purchase_items_company_id_product_id", "purchase_items", ["company_id", "product_id"]
    )

    enable_tenant_rls(op, "purchases")
    enable_tenant_rls(op, "purchase_items")


def downgrade() -> None:
    disable_tenant_rls(op, "purchase_items")
    disable_tenant_rls(op, "purchases")
    op.drop_table("purchase_items")
    op.drop_table("purchases")
