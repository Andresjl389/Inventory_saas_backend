"""Categories and products, with the standard tenant RLS policies.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.infrastructure.database.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(18, 4)


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", PGUUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_categories_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("company_id", "name", name="uq_categories_company_id_name"),
    )
    op.create_index("ix_categories_company_id", "categories", ["company_id"])

    op.create_table(
        "products",
        sa.Column("id", PGUUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("category_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("barcode", sa.String(64), nullable=True),
        sa.Column("cost_price", MONEY, nullable=False, server_default="0"),
        sa.Column("sale_price", MONEY, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_products_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_products_category_id_categories",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("cost_price >= 0", name="ck_products_cost_price_non_negative"),
        sa.CheckConstraint("sale_price >= 0", name="ck_products_sale_price_non_negative"),
        sa.UniqueConstraint("company_id", "sku", name="uq_products_company_id_sku"),
    )
    op.create_index("ix_products_company_id", "products", ["company_id"])
    op.create_index("ix_products_company_id_is_active", "products", ["company_id", "is_active"])
    op.create_index("ix_products_company_id_category_id", "products", ["company_id", "category_id"])
    # Partial: barcode is optional, so only non-null values must be unique.
    op.create_index(
        "uq_products_company_id_barcode",
        "products",
        ["company_id", "barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )

    enable_tenant_rls(op, "categories")
    enable_tenant_rls(op, "products")


def downgrade() -> None:
    disable_tenant_rls(op, "products")
    disable_tenant_rls(op, "categories")

    op.drop_index("uq_products_company_id_barcode", table_name="products")
    op.drop_index("ix_products_company_id_category_id", table_name="products")
    op.drop_index("ix_products_company_id_is_active", table_name="products")
    op.drop_index("ix_products_company_id", table_name="products")
    op.drop_table("products")

    op.drop_index("ix_categories_company_id", table_name="categories")
    op.drop_table("categories")
