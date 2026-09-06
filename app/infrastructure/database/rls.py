"""Helpers to declare PostgreSQL Row Level Security from Alembic migrations.

RLS is part of the schema, so it lives in the migrations -- never in a side
script that somebody has to remember to run (BACKEND.md section 33).
"""

TENANT_SETTING = "app.current_company_id"
USER_SETTING = "app.current_user_id"


def enable_tenant_rls(op, table: str, *, column: str = "company_id") -> None:
    """Enable + FORCE RLS on `table` and add the four tenant policies.

    FORCE matters: without it the table owner (the role Alembic runs as, and
    usually the role the app connects as) would silently bypass every policy.
    """
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(
        f"""
        CREATE POLICY {table}_tenant_select ON {table}
        FOR SELECT
        USING ({column} = app.current_company_id())
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_tenant_insert ON {table}
        FOR INSERT
        WITH CHECK ({column} = app.current_company_id())
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_tenant_update ON {table}
        FOR UPDATE
        USING ({column} = app.current_company_id())
        WITH CHECK ({column} = app.current_company_id())
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_tenant_delete ON {table}
        FOR DELETE
        USING ({column} = app.current_company_id())
        """
    )


def disable_tenant_rls(op, table: str) -> None:
    for action in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_{action} ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
