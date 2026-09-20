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

    missing = {name: counts.get(name, 0) for name in names if counts.get(name, 0) < 4}
    assert missing == {}, f"tables missing SELECT/INSERT/UPDATE/DELETE policies: {missing}"


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
