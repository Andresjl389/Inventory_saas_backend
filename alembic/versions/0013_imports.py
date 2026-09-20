"""Bulk imports: jobs and their row-level errors.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.domain.imports.entities.import_job import ImportStatus
from app.domain.imports.schemas import ImportEntity
from app.infrastructure.database.migration_helpers import (
    enum_column,
    timestamps,
    uuid_column,
    uuid_pk,
)
from app.infrastructure.database.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENTITIES = tuple(item.value for item in ImportEntity)
STATUSES = tuple(item.value for item in ImportStatus)

IMPORT_PERMISSIONS = (
    ("imports.read", "imports", "View imports and their errors"),
    ("imports.run", "imports", "Upload files and load them into the company"),
)
IMPORT_GRANTS = {
    "ADMIN": ("imports.read", "imports.run"),
    "INVENTORY_MANAGER": ("imports.read", "imports.run"),
    "SELLER": ("imports.read",),
}


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        uuid_pk(),
        uuid_column("company_id"),
        enum_column("entity", ENTITIES, "import_entity", nullable=False),
        uuid_column("file_id"),
        sa.Column("filename", sa.String(255), nullable=False),
        enum_column("status", STATUSES, "import_status", nullable=False, server_default="ANALYZED"),
        sa.Column("mapping", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("options", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("detected_columns", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("stats", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        uuid_column("created_by", nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_import_jobs"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_import_jobs_company_id_companies",
            ondelete="CASCADE",
        ),
        # Deleting the uploaded file takes its import history with it; the file
        # is the only record of what was actually loaded.
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name="fk_import_jobs_file_id_files", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_import_jobs_created_by_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_import_jobs_company_id", "import_jobs", ["company_id"])
    op.create_index(
        "ix_import_jobs_company_id_created_at", "import_jobs", ["company_id", "created_at"]
    )
    op.create_index("ix_import_jobs_company_id_status", "import_jobs", ["company_id", "status"])

    op.create_table(
        "import_errors",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("job_id"),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("column", sa.String(255), nullable=True),
        sa.Column("field_key", sa.String(64), nullable=True),
        sa.Column("value", sa.String(500), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_import_errors"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_import_errors_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["import_jobs.id"],
            name="fk_import_errors_job_id_import_jobs",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_import_errors_company_id", "import_errors", ["company_id"])
    op.create_index("ix_import_errors_job_id_row_number", "import_errors", ["job_id", "row_number"])

    enable_tenant_rls(op, "import_jobs")
    enable_tenant_rls(op, "import_errors")
    _seed_import_permissions()


def _seed_import_permissions() -> None:
    # A migration is a platform operation; SET LOCAL keeps the flag to this
    # transaction. Written idempotently because a fresh database already gets
    # these codes from 0008, which seeds the whole catalogue.
    op.execute("SET LOCAL app.is_platform_admin = 'true'")

    for code, module, description in IMPORT_PERMISSIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO permissions (code, module, description)
                VALUES (:code, :module, :description)
                ON CONFLICT (code) DO NOTHING
                """
            ).bindparams(code=code, module=module, description=description)
        )

    for role_code, codes in IMPORT_GRANTS.items():
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
    disable_tenant_rls(op, "import_errors")
    disable_tenant_rls(op, "import_jobs")
    op.drop_table("import_errors")
    op.drop_table("import_jobs")
    op.execute("SET LOCAL app.is_platform_admin = 'true'")
    op.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(
            codes=[code for code, _, _ in IMPORT_PERMISSIONS]
        )
    )
