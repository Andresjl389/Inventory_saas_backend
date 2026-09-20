"""Structural guard: no tenant table may ship without RLS.

The isolation tests in test_rls_isolation.py prove the policies work for the
tables they exercise. This file proves nobody added a *new* tenant table and
forgot the policies -- the failure mode that silently reopens cross-tenant
access as the schema grows.
"""

import pytest
from sqlalchemy import text

from tests.conftest import requires_db

pytestmark = requires_db

# `companies` scopes by its own primary key rather than a company_id column, so
# it is checked separately below.
SELF_SCOPED_TABLES = {"companies"}

# The audit log is append-only: it has SELECT and INSERT policies and
# deliberately no UPDATE or DELETE, so nobody can rewrite history.
APPEND_ONLY_TABLES = {"audit_logs"}

# No company_id of their own -- they inherit scope from the role they belong to
# (role_permissions) or are a global catalogue (permissions, plans).
SCOPE_BY_ASSOCIATION = {"role_permissions", "permissions", "plans"}

TENANT_TABLES_WITH_COLUMN = """
    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'company_id' AND a.attnum > 0
    WHERE n.nspname = 'public' AND c.relkind = 'r'
    ORDER BY c.relname
"""


async def test_every_table_with_a_company_id_has_forced_rls(session):
    rows = (await session.execute(text(TENANT_TABLES_WITH_COLUMN))).all()

    assert rows, "expected the schema to contain tenant tables"
    unprotected = [name for name, enabled, forced in rows if not (enabled and forced)]

    assert unprotected == [], (
        f"tables carry company_id but are not protected by FORCE ROW LEVEL SECURITY: "
        f"{unprotected}. Add enable_tenant_rls(op, '<table>') to their migration."
    )


async def test_every_tenant_table_has_all_four_policies(session):
    names = [row[0] for row in (await session.execute(text(TENANT_TABLES_WITH_COLUMN))).all()]
    names += sorted(SELF_SCOPED_TABLES)

    counts = dict(
        (
            await session.execute(
                text(
                    """
                    SELECT tablename, count(DISTINCT cmd)
                    FROM pg_policies
                    WHERE schemaname = 'public'
                    GROUP BY tablename
                    """
                )
            )
        ).all()
    )

    expected = {name: 2 if name in APPEND_ONLY_TABLES else 4 for name in names}
    missing = {
        name: counts.get(name, 0)
        for name, minimum in expected.items()
        if counts.get(name, 0) < minimum
    }
    assert missing == {}, f"tables missing the policies they need: {missing}"


async def test_the_audit_log_cannot_be_rewritten(session):
    """History is append-only: no UPDATE or DELETE policy exists for anyone,
    platform admins included."""
    commands = (
        (
            await session.execute(
                text(
                    """
                SELECT cmd FROM pg_policies
                WHERE schemaname = 'public' AND tablename = 'audit_logs'
                """
                )
            )
        )
        .scalars()
        .all()
    )

    assert set(commands) == {"SELECT", "INSERT"}


async def test_the_global_catalogues_are_read_only_for_tenants(session):
    """permissions and plans are readable by every tenant and writable only
    with the platform flag raised."""
    for table in ("permissions", "plans"):
        rows = dict(
            (
                await session.execute(
                    text(
                        """
                        SELECT cmd, coalesce(qual, with_check) FROM pg_policies
                        WHERE schemaname = 'public' AND tablename = :table
                        """
                    ),
                    {"table": table},
                )
            ).all()
        )
        assert rows["SELECT"] == "true", f"{table} should be world-readable"
        for command in ("INSERT", "UPDATE", "DELETE"):
            assert "is_platform_admin" in rows[command], (
                f"{table} {command} should require the platform flag"
            )


@pytest.mark.parametrize(
    "table",
    ["warehouses", "product_stock", "stock_movements", "customers", "suppliers"],
)
async def test_tenant_tables_are_invisible_without_a_company_context(session, table):
    await session.execute(text("SELECT set_config('app.current_company_id', '', true)"))
    visible = (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
    assert visible == 0


async def test_sale_items_are_scoped_too(session):
    """The line items are the detail that leaks a sale even when the header is
    hidden, so they carry their own company_id and their own policies."""
    await session.execute(text("SELECT set_config('app.current_company_id', '', true)"))

    for table in ("sales", "sale_items", "purchases", "purchase_items"):
        count = (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
        assert count == 0, f"{table} leaked rows without a tenant context"
