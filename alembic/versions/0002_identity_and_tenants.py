"""Users, companies, company members and their RLS policies.

`users` is not tenant-owned and carries no RLS. `companies` and
`company_members` need bespoke policies (BACKEND.md section 23): membership is
what grants visibility, so the policies read app.current_user_id() as well as
app.current_company_id().

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_TYPES = ("NIT", "CC", "CE", "PASSPORT", "RUT", "OTHER")
COMPANY_STATUSES = ("ACTIVE", "SUSPENDED", "INACTIVE")
COMPANY_ROLES = ("OWNER", "ADMIN", "SELLER", "INVENTORY_MANAGER")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", PGUUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "companies",
        sa.Column("id", PGUUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("legal_name", sa.String(200), nullable=True),
        sa.Column(
            "document_type",
            sa.Enum(*DOCUMENT_TYPES, name="document_type", native_enum=False, length=32),
            nullable=True,
        ),
        sa.Column("document_number", sa.String(50), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*COMPANY_STATUSES, name="company_status", native_enum=False, length=32),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
        sa.UniqueConstraint(
            "document_type", "document_number", name="uq_companies_document_type_document_number"
        ),
    )

    op.create_table(
        "company_members",
        sa.Column("id", PGUUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("user_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.Enum(*COMPANY_ROLES, name="company_role", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_company_members"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_company_members_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_company_members_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("company_id", "user_id", name="uq_company_members_company_id_user_id"),
    )
    op.create_index("ix_company_members_user_id", "company_members", ["user_id"])
    op.create_index("ix_company_members_company_id", "company_members", ["company_id"])

    _create_company_policies()
    _create_company_member_policies()


def _create_company_policies() -> None:
    op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE companies FORCE ROW LEVEL SECURITY")

    # Readable when it is the active tenant, or when the caller holds an active
    # membership (this is what powers the "my companies" switcher, which runs
    # before any company has been selected).
    op.execute(
        """
        CREATE POLICY companies_select ON companies
        FOR SELECT
        USING (
            id = app.current_company_id()
            OR EXISTS (
                SELECT 1 FROM company_members cm
                WHERE cm.company_id = companies.id
                  AND cm.user_id = app.current_user_id()
                  AND cm.is_active
            )
        )
        """
    )
    # Creating a company means entering its scope first (see
    # CreateCompanyUseCase), so the row always matches the active tenant.
    op.execute(
        """
        CREATE POLICY companies_insert ON companies
        FOR INSERT
        WITH CHECK (id = app.current_company_id())
        """
    )
    op.execute(
        """
        CREATE POLICY companies_update ON companies
        FOR UPDATE
        USING (id = app.current_company_id())
        WITH CHECK (id = app.current_company_id())
        """
    )
    op.execute(
        """
        CREATE POLICY companies_delete ON companies
        FOR DELETE
        USING (id = app.current_company_id())
        """
    )


def _create_company_member_policies() -> None:
    op.execute("ALTER TABLE company_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE company_members FORCE ROW LEVEL SECURITY")

    # A user always sees their own memberships; inside a tenant they see the
    # whole roster.
    op.execute(
        """
        CREATE POLICY company_members_select ON company_members
        FOR SELECT
        USING (
            user_id = app.current_user_id()
            OR company_id = app.current_company_id()
        )
        """
    )
    op.execute(
        """
        CREATE POLICY company_members_insert ON company_members
        FOR INSERT
        WITH CHECK (company_id = app.current_company_id())
        """
    )
    op.execute(
        """
        CREATE POLICY company_members_update ON company_members
        FOR UPDATE
        USING (company_id = app.current_company_id())
        WITH CHECK (company_id = app.current_company_id())
        """
    )
    op.execute(
        """
        CREATE POLICY company_members_delete ON company_members
        FOR DELETE
        USING (company_id = app.current_company_id())
        """
    )


def downgrade() -> None:
    for table in ("company_members", "companies"):
        for action in ("select", "insert", "update", "delete"):
            op.execute(f"DROP POLICY IF EXISTS {table}_{action} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_company_members_company_id", table_name="company_members")
    op.drop_index("ix_company_members_user_id", table_name="company_members")
    op.drop_table("company_members")
    op.drop_table("companies")
    op.drop_table("users")
