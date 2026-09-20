"""Database-backed roles and permissions, plus the platform-admin escape hatch.

Replaces the hard-coded role enum on company_members with a `roles` row, so a
company can define its own roles without a deploy. The four system roles are
seeded here from app.domain.authorization.permissions, which stays the single
source of truth for the catalogue.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.domain.authorization.permissions import (
    CATALOG,
    SYSTEM_ROLE_NAMES,
    SYSTEM_ROLE_PERMISSIONS,
)
from app.infrastructure.database.migration_helpers import timestamps, uuid_column, uuid_pk

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_platform_admin_function()
    _create_tables()
    # Seed before enabling RLS: the migration runs with no tenant context and
    # no admin flag, so the INSERT policies would reject its own seed data.
    _seed_catalog()
    _migrate_company_members()
    _enable_rls()
    _widen_company_policies()


def _create_platform_admin_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.is_platform_admin()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            SELECT COALESCE(
                NULLIF(current_setting('app.is_platform_admin', true), '')::boolean,
                false
            );
        $$;
        """
    )


def _create_tables() -> None:
    op.create_table(
        "permissions",
        uuid_pk(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )

    op.create_table(
        "roles",
        uuid_pk(),
        uuid_column("company_id", nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_roles_company_id_companies",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_roles_company_id", "roles", ["company_id"])
    # UNIQUE(company_id, code) would be useless for system roles: every NULL
    # company_id counts as distinct. Two partial indexes instead.
    op.create_index(
        "uq_roles_system_code",
        "roles",
        ["code"],
        unique=True,
        postgresql_where=sa.text("company_id IS NULL"),
    )
    op.create_index(
        "uq_roles_company_id_code",
        "roles",
        ["company_id", "code"],
        unique=True,
        postgresql_where=sa.text("company_id IS NOT NULL"),
    )

    op.create_table(
        "role_permissions",
        uuid_column("role_id"),
        uuid_column("permission_id"),
        *timestamps(),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_role_permissions_role_id_roles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])


def _seed_catalog() -> None:
    permissions = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("module", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        permissions,
        [
            {"code": item.code, "module": item.module, "description": item.description}
            for item in CATALOG
        ],
    )

    roles = sa.table(
        "roles",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_system", sa.Boolean),
    )
    op.bulk_insert(
        roles,
        [
            {
                "code": role.value,
                "name": SYSTEM_ROLE_NAMES[role],
                "description": f"Built-in {SYSTEM_ROLE_NAMES[role].lower()} role",
                "is_system": True,
            }
            for role in SYSTEM_ROLE_PERMISSIONS
        ],
    )

    for role, codes in SYSTEM_ROLE_PERMISSIONS.items():
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
                """
            ).bindparams(role_code=role.value, permission_codes=sorted(codes))
        )


def _migrate_company_members() -> None:
    op.add_column(
        "company_members",
        sa.Column("role_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE company_members cm
        SET role_id = r.id
        FROM roles r
        WHERE r.company_id IS NULL AND r.code = cm.role
        """
    )
    # Any membership whose role code has no matching system role would be
    # orphaned; there is none, and NOT NULL below would catch it loudly.
    op.alter_column("company_members", "role_id", nullable=False)
    op.create_foreign_key(
        "fk_company_members_role_id_roles",
        "company_members",
        "roles",
        ["role_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_company_members_role_id", "company_members", ["role_id"])
    op.drop_column("company_members", "role")


def _enable_rls() -> None:
    # permissions: a read-only catalogue for tenants.
    op.execute("ALTER TABLE permissions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE permissions FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY permissions_tenant_select ON permissions FOR SELECT USING (true)")
    for action, clause in (
        ("insert", "WITH CHECK (app.is_platform_admin())"),
        ("update", "USING (app.is_platform_admin()) WITH CHECK (app.is_platform_admin())"),
        ("delete", "USING (app.is_platform_admin())"),
    ):
        op.execute(
            f"CREATE POLICY permissions_tenant_{action} ON permissions "
            f"FOR {action.upper()} {clause}"
        )

    # roles: system roles are visible to everyone and editable by nobody but
    # the platform; a company owns only its own rows.
    own_role = "(company_id = app.current_company_id() AND is_system = false)"
    op.execute("ALTER TABLE roles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE roles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY roles_tenant_select ON roles FOR SELECT
        USING (
            company_id IS NULL
            OR company_id = app.current_company_id()
            OR app.is_platform_admin()
            -- A user must be able to see a role they actually hold even with no
            -- company selected: the company switcher lists each membership's
            -- role, and that request runs before any tenant scope exists.
            OR EXISTS (
                SELECT 1 FROM company_members cm
                WHERE cm.role_id = roles.id
                  AND cm.user_id = app.current_user_id()
            )
        )
        """
    )
    op.execute(
        f"CREATE POLICY roles_tenant_insert ON roles FOR INSERT "
        f"WITH CHECK ({own_role} OR app.is_platform_admin())"
    )
    op.execute(
        f"CREATE POLICY roles_tenant_update ON roles FOR UPDATE "
        f"USING ({own_role} OR app.is_platform_admin()) "
        f"WITH CHECK ({own_role} OR app.is_platform_admin())"
    )
    op.execute(
        f"CREATE POLICY roles_tenant_delete ON roles FOR DELETE "
        f"USING ({own_role} OR app.is_platform_admin())"
    )

    # role_permissions has no company_id: it inherits scope from its role, and
    # the subquery is itself filtered by the policies above.
    writable_role = """
        EXISTS (
            SELECT 1 FROM roles r
            WHERE r.id = role_permissions.role_id
              AND (
                  (r.company_id = app.current_company_id() AND r.is_system = false)
                  OR app.is_platform_admin()
              )
        )
    """
    op.execute("ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE role_permissions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY role_permissions_tenant_select ON role_permissions FOR SELECT
        USING (EXISTS (SELECT 1 FROM roles r WHERE r.id = role_permissions.role_id))
        """
    )
    op.execute(
        f"CREATE POLICY role_permissions_tenant_insert ON role_permissions "
        f"FOR INSERT WITH CHECK ({writable_role})"
    )
    op.execute(
        f"CREATE POLICY role_permissions_tenant_update ON role_permissions "
        f"FOR UPDATE USING ({writable_role}) WITH CHECK ({writable_role})"
    )
    op.execute(
        f"CREATE POLICY role_permissions_tenant_delete ON role_permissions "
        f"FOR DELETE USING ({writable_role})"
    )


def _widen_company_policies() -> None:
    """Let a platform admin see companies and memberships across tenants.

    Business tables are deliberately left alone: an operator who wants a
    tenant's products or sales has to enter that company first.
    """
    for action in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS companies_{action} ON companies")
        op.execute(f"DROP POLICY IF EXISTS company_members_{action} ON company_members")

    op.execute(
        """
        CREATE POLICY companies_tenant_select ON companies FOR SELECT
        USING (
            id = app.current_company_id()
            OR app.is_platform_admin()
            OR EXISTS (
                SELECT 1 FROM company_members cm
                WHERE cm.company_id = companies.id
                  AND cm.user_id = app.current_user_id()
                  AND cm.is_active
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY companies_tenant_insert ON companies FOR INSERT
        WITH CHECK (id = app.current_company_id() OR app.is_platform_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY companies_tenant_update ON companies FOR UPDATE
        USING (id = app.current_company_id() OR app.is_platform_admin())
        WITH CHECK (id = app.current_company_id() OR app.is_platform_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY companies_tenant_delete ON companies FOR DELETE
        USING (id = app.current_company_id() OR app.is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE POLICY company_members_tenant_select ON company_members FOR SELECT
        USING (
            user_id = app.current_user_id()
            OR company_id = app.current_company_id()
            OR app.is_platform_admin()
        )
        """
    )
    scope = "(company_id = app.current_company_id() OR app.is_platform_admin())"
    op.execute(
        f"CREATE POLICY company_members_tenant_insert ON company_members "
        f"FOR INSERT WITH CHECK {scope}"
    )
    op.execute(
        f"CREATE POLICY company_members_tenant_update ON company_members "
        f"FOR UPDATE USING {scope} WITH CHECK {scope}"
    )
    op.execute(
        f"CREATE POLICY company_members_tenant_delete ON company_members FOR DELETE USING {scope}"
    )


def downgrade() -> None:
    for table in ("role_permissions", "roles", "permissions"):
        for action in ("select", "insert", "update", "delete"):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_{action} ON {table}")

    op.add_column(
        "company_members",
        sa.Column(
            "role",
            sa.Enum(
                "OWNER",
                "ADMIN",
                "SELLER",
                "INVENTORY_MANAGER",
                name="company_role",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE company_members cm
        SET role = r.code
        FROM roles r
        WHERE r.id = cm.role_id
          AND r.code IN ('OWNER', 'ADMIN', 'SELLER', 'INVENTORY_MANAGER')
        """
    )
    op.execute("UPDATE company_members SET role = 'ADMIN' WHERE role IS NULL")
    op.alter_column("company_members", "role", nullable=False)

    op.drop_index("ix_company_members_role_id", table_name="company_members")
    op.drop_constraint("fk_company_members_role_id_roles", "company_members", type_="foreignkey")
    op.drop_column("company_members", "role_id")

    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")

    for action in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS companies_tenant_{action} ON companies")
        op.execute(f"DROP POLICY IF EXISTS company_members_tenant_{action} ON company_members")

    op.execute(
        """
        CREATE POLICY companies_select ON companies FOR SELECT
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
    op.execute(
        "CREATE POLICY companies_insert ON companies FOR INSERT "
        "WITH CHECK (id = app.current_company_id())"
    )
    op.execute(
        "CREATE POLICY companies_update ON companies FOR UPDATE "
        "USING (id = app.current_company_id()) WITH CHECK (id = app.current_company_id())"
    )
    op.execute(
        "CREATE POLICY companies_delete ON companies FOR DELETE "
        "USING (id = app.current_company_id())"
    )
    op.execute(
        """
        CREATE POLICY company_members_select ON company_members FOR SELECT
        USING (user_id = app.current_user_id() OR company_id = app.current_company_id())
        """
    )
    for action in ("insert", "update", "delete"):
        clause = {
            "insert": "WITH CHECK (company_id = app.current_company_id())",
            "update": (
                "USING (company_id = app.current_company_id()) "
                "WITH CHECK (company_id = app.current_company_id())"
            ),
            "delete": "USING (company_id = app.current_company_id())",
        }[action]
        op.execute(
            f"CREATE POLICY company_members_{action} ON company_members "
            f"FOR {action.upper()} {clause}"
        )

    op.execute("DROP FUNCTION IF EXISTS app.is_platform_admin()")
