"""Sales and sale items.

Revision ID: 0006
Revises: 0005
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

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SALE_STATUSES = ("DRAFT", "COMPLETED", "CANCELLED", "REFUNDED")


def upgrade() -> None:
    op.create_table(
        "sales",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("customer_id", nullable=True),
        uuid_column("warehouse_id"),
        enum_column("status", SALE_STATUSES, "sale_status", nullable=False, server_default="DRAFT"),
        money_column("subtotal"),
        money_column("discount"),
        money_column("tax"),
        money_column("total"),
        sa.Column("notes", sa.Text(), nullable=True),
        uuid_column("created_by", nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_sales"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_sales_company_id_companies",
            ondelete="CASCADE",
        ),
        # RESTRICT: a customer with sales history is deactivated, never deleted.
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_sales_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_sales_warehouse_id_warehouses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_sales_created_by_users", ondelete="SET NULL"
        ),
        sa.CheckConstraint("total >= 0", name="ck_sales_total_non_negative"),
    )
    op.create_index("ix_sales_company_id", "sales", ["company_id"])
    op.create_index("ix_sales_company_id_created_at", "sales", ["company_id", "created_at"])
    op.create_index("ix_sales_company_id_status", "sales", ["company_id", "status"])
    op.create_index("ix_sales_company_id_customer_id", "sales", ["company_id", "customer_id"])

    op.create_table(
        "sale_items",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("sale_id"),
        uuid_column("product_id"),
        quantity_column("quantity"),
        money_column("unit_price", default=None),
        money_column("discount"),
        money_column("tax"),
        money_column("total"),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_sale_items"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_sale_items_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sale_id"], ["sales.id"], name="fk_sale_items_sale_id_sales", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_sale_items_product_id_products",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_sale_items_unit_price_non_negative"),
        sa.CheckConstraint("total >= 0", name="ck_sale_items_total_non_negative"),
    )
    op.create_index("ix_sale_items_company_id", "sale_items", ["company_id"])
    op.create_index("ix_sale_items_sale_id", "sale_items", ["sale_id"])
    op.create_index(
        "ix_sale_items_company_id_product_id", "sale_items", ["company_id", "product_id"]
    )

    enable_tenant_rls(op, "sales")
    enable_tenant_rls(op, "sale_items")


def downgrade() -> None:
    disable_tenant_rls(op, "sale_items")
    disable_tenant_rls(op, "sales")
    op.drop_table("sale_items")
    op.drop_table("sales")
