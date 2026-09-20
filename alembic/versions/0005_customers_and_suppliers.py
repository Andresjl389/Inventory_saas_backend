"""Customers and suppliers.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.infrastructure.database.migration_helpers import (
    enum_column,
    timestamps,
    uuid_column,
    uuid_pk,
)
from app.infrastructure.database.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_TYPES = ("NIT", "CC", "CE", "PASSPORT", "RUT", "OTHER")


def _party_table(name: str) -> None:
    op.create_table(
        name,
        uuid_pk(),
        uuid_column("company_id"),
        sa.Column("name", sa.String(200), nullable=False),
        enum_column("document_type", DOCUMENT_TYPES, "document_type", nullable=True),
        sa.Column("document_number", sa.String(50), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=f"pk_{name}"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=f"fk_{name}_company_id_companies",
            ondelete="CASCADE",
        ),
        # Scoped to the tenant: two companies may well share a customer.
        sa.UniqueConstraint(
            "company_id",
            "document_type",
            "document_number",
            name=f"uq_{name}_company_id_document_type_document_number",
        ),
    )
    op.create_index(f"ix_{name}_company_id", name, ["company_id"])
    op.create_index(f"ix_{name}_company_id_is_active", name, ["company_id", "is_active"])
    op.create_index(f"ix_{name}_company_id_name", name, ["company_id", "name"])
    enable_tenant_rls(op, name)


def upgrade() -> None:
    _party_table("customers")
    _party_table("suppliers")


def downgrade() -> None:
    for name in ("suppliers", "customers"):
        disable_tenant_rls(op, name)
        op.drop_table(name)
