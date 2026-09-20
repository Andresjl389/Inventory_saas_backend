"""Audit log.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.domain.audit.entities.audit_entry import AuditAction
from app.infrastructure.database.migration_helpers import enum_column, uuid_column, uuid_pk
from app.infrastructure.database.rls import disable_tenant_rls, enable_platform_tenant_rls

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = tuple(action.value for action in AuditAction)


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        uuid_pk(),
        # NULL for platform-level actions, which belong to no tenant.
        uuid_column("company_id", nullable=True),
        uuid_column("actor_user_id", nullable=True),
        enum_column("action", ACTIONS, "audit_action", nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        uuid_column("entity_id", nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_audit_logs_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_logs_actor_user_id_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_logs_company_id", "audit_logs", ["company_id"])
    op.create_index(
        "ix_audit_logs_company_id_created_at", "audit_logs", ["company_id", "created_at"]
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    enable_platform_tenant_rls(op, "audit_logs")
    # Rows with company_id NULL are platform events: only an operator sees them,
    # and the standard policy's `company_id = current` can never match a NULL.
    op.execute("DROP POLICY IF EXISTS audit_logs_tenant_insert ON audit_logs")
    op.execute(
        """
        CREATE POLICY audit_logs_tenant_insert ON audit_logs FOR INSERT
        WITH CHECK (
            company_id = app.current_company_id()
            OR (company_id IS NULL AND app.is_platform_admin())
            OR app.is_platform_admin()
        )
        """
    )
    # The log is append-only: no UPDATE, no DELETE, for anybody.
    op.execute("DROP POLICY IF EXISTS audit_logs_tenant_update ON audit_logs")
    op.execute("DROP POLICY IF EXISTS audit_logs_tenant_delete ON audit_logs")


def downgrade() -> None:
    disable_tenant_rls(op, "audit_logs")
    op.drop_table("audit_logs")
