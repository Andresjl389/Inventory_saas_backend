"""Warehouses, current stock and the stock movement ledger.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.infrastructure.database.migration_helpers import (
    enum_column,
    money_column,  # noqa: F401  (kept for symmetry with later migrations)
    quantity_column,
    timestamps,
    uuid_column,
    uuid_pk,
)
from app.infrastructure.database.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOVEMENT_TYPES = (
    "PURCHASE",
    "SALE",
    "RETURN",
    "ADJUSTMENT",
    "TRANSFER_IN",
    "TRANSFER_OUT",
)
REFERENCE_TYPES = ("SALE", "PURCHASE", "TRANSFER", "MANUAL")


def upgrade() -> None:
    op.create_table(
        "warehouses",
        uuid_pk(),
        uuid_column("company_id"),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_warehouses"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_warehouses_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("company_id", "name", name="uq_warehouses_company_id_name"),
    )
    op.create_index("ix_warehouses_company_id", "warehouses", ["company_id"])
    op.create_index("ix_warehouses_company_id_is_active", "warehouses", ["company_id", "is_active"])

    op.create_table(
        "product_stock",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("product_id"),
        uuid_column("warehouse_id"),
        quantity_column("quantity", default="0"),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_product_stock"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_product_stock_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_stock_product_id_products",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_product_stock_warehouse_id_warehouses",
            ondelete="CASCADE",
        ),
        # The upsert in StockRepository.lock_for_update targets this constraint.
        sa.UniqueConstraint(
            "company_id",
            "product_id",
            "warehouse_id",
            name="uq_product_stock_company_id_product_id_warehouse_id",
        ),
    )
    op.create_index("ix_product_stock_company_id", "product_stock", ["company_id"])
    op.create_index(
        "ix_product_stock_company_id_warehouse_id",
        "product_stock",
        ["company_id", "warehouse_id"],
    )

    op.create_table(
        "stock_movements",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("product_id"),
        uuid_column("warehouse_id"),
        enum_column("movement_type", MOVEMENT_TYPES, "movement_type", nullable=False),
        # Signed delta, so SUM(quantity) reconstructs product_stock.quantity.
        quantity_column("quantity"),
        enum_column(
            "reference_type",
            REFERENCE_TYPES,
            "reference_type",
            nullable=False,
            server_default="MANUAL",
        ),
        uuid_column("reference_id", nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        uuid_column("created_by", nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stock_movements"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_stock_movements_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_stock_movements_product_id_products",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_stock_movements_warehouse_id_warehouses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_stock_movements_created_by_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("quantity <> 0", name="ck_stock_movements_quantity_not_zero"),
        # The sign has to match the movement type, or the ledger stops being a
        # reliable reconstruction of current stock.
        sa.CheckConstraint(
            """
            (movement_type IN ('PURCHASE', 'RETURN', 'TRANSFER_IN') AND quantity > 0)
            OR (movement_type IN ('SALE', 'TRANSFER_OUT') AND quantity < 0)
            OR movement_type = 'ADJUSTMENT'
            """,
            name="ck_stock_movements_quantity_sign_matches_type",
        ),
    )
    op.create_index("ix_stock_movements_company_id", "stock_movements", ["company_id"])
    op.create_index(
        "ix_stock_movements_company_id_created_at", "stock_movements", ["company_id", "created_at"]
    )
    op.create_index(
        "ix_stock_movements_company_id_product_id_warehouse_id",
        "stock_movements",
        ["company_id", "product_id", "warehouse_id"],
    )
    op.create_index(
        "ix_stock_movements_company_id_reference_id",
        "stock_movements",
        ["company_id", "reference_id"],
    )

    for table in ("warehouses", "product_stock", "stock_movements"):
        enable_tenant_rls(op, table)


def downgrade() -> None:
    for table in ("stock_movements", "product_stock", "warehouses"):
        disable_tenant_rls(op, table)

    op.drop_table("stock_movements")
    op.drop_table("product_stock")
    op.drop_table("warehouses")
