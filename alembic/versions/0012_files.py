"""File metadata.

The bytes live outside PostgreSQL (BACKEND.md section 42) -- today in a local
folder, later in an S3 bucket. This table is what makes a blob findable and,
through RLS, what keeps one tenant's uploads invisible to another.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.domain.files.entities.stored_file import FileOwnerType
from app.infrastructure.database.migration_helpers import (
    enum_column,
    timestamps,
    uuid_column,
    uuid_pk,
)
from app.infrastructure.database.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_TYPES = tuple(item.value for item in FileOwnerType)


def upgrade() -> None:
    op.create_table(
        "files",
        uuid_pk(),
        uuid_column("company_id"),
        enum_column("owner_type", OWNER_TYPES, "file_owner_type", nullable=False),
        # No foreign key: owner_id points at whichever table owner_type names,
        # and one column cannot reference several. The application validates it.
        uuid_column("owner_id", nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        uuid_column("uploaded_by", nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_files"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_files_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name="fk_files_uploaded_by_users",
            ondelete="SET NULL",
        ),
        # One row per blob: it is what the orphan sweep matches on.
        sa.UniqueConstraint("storage_key", name="uq_files_storage_key"),
        sa.CheckConstraint("size_bytes > 0", name="ck_files_size_bytes_positive"),
    )
    op.create_index("ix_files_company_id", "files", ["company_id"])
    op.create_index(
        "ix_files_company_id_owner_type_owner_id",
        "files",
        ["company_id", "owner_type", "owner_id"],
    )
    op.create_index("ix_files_company_id_created_at", "files", ["company_id", "created_at"])

    enable_tenant_rls(op, "files")
    _seed_file_permissions()


# Written idempotently because a fresh database gets these two codes from
# migration 0008 (which seeds the whole catalogue, and the catalogue now lists
# them), while a database already at 0011 sees them for the first time here.
FILE_PERMISSIONS = (
    ("files.read", "files", "View and download attachments"),
    ("files.write", "files", "Upload and delete attachments"),
)
FILE_GRANTS = {
    "ADMIN": ("files.read", "files.write"),
    "INVENTORY_MANAGER": ("files.read", "files.write"),
    "SELLER": ("files.read",),
}


def _seed_file_permissions() -> None:
    # `permissions` and `role_permissions` only accept writes from a platform
    # operator, and a migration is exactly that. SET LOCAL keeps the flag to
    # this transaction, so it is gone the moment the migration commits.
    op.execute("SET LOCAL app.is_platform_admin = 'true'")

    for code, module, description in FILE_PERMISSIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO permissions (code, module, description)
                VALUES (:code, :module, :description)
                ON CONFLICT (code) DO NOTHING
                """
            ).bindparams(code=code, module=module, description=description)
        )

    for role_code, codes in FILE_GRANTS.items():
        op.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM roles r
                CROSS JOIN permissions p
                WHERE r.company_id IS NULL
                  AND r.code = :role_code
                  AND p.code = ANY(:permission_codes)
                ON CONFLICT DO NOTHING
                """
            ).bindparams(role_code=role_code, permission_codes=sorted(codes))
        )


def downgrade() -> None:
    disable_tenant_rls(op, "files")
    op.drop_table("files")
    op.execute("SET LOCAL app.is_platform_admin = 'true'")
    op.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(
            codes=[code for code, _, _ in FILE_PERMISSIONS]
        )
    )
