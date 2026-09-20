"""Helpers to declare PostgreSQL Row Level Security from Alembic migrations.

RLS is part of the schema, so it lives in the migrations -- never in a side
script that somebody has to remember to run (BACKEND.md section 33).

Three shapes of policy, and the difference matters:

* `enable_tenant_rls` -- business data (products, sales, stock...). Scoped
  strictly to `app.current_company_id()`, with **no** platform-admin escape.
  An operator who needs to look at a tenant's data must step into that company,
  which keeps every request single-tenant and auditable.
* `enable_platform_tenant_rls` -- the tables the platform is made of
  (companies, memberships, roles, subscriptions, audit log). A platform admin
  legitimately lists these across tenants, so the policies add
  `OR app.is_platform_admin()`.
* `enable_catalog_rls` -- global catalogues (permissions, plans). Readable by
  everyone, writable only by a platform admin.
"""

TENANT_SETTING = "app.current_company_id"
USER_SETTING = "app.current_user_id"
ADMIN_SETTING = "app.is_platform_admin"

_ADMIN = "app.is_platform_admin()"


def _policies(op, table: str, *, select: str, insert: str, update: str, delete: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    # FORCE matters: without it the table owner (the role Alembic runs as, and
    # usually the role the app connects as) would silently bypass every policy.
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(f"CREATE POLICY {table}_tenant_select ON {table} FOR SELECT USING ({select})")
    op.execute(f"CREATE POLICY {table}_tenant_insert ON {table} FOR INSERT WITH CHECK ({insert})")
    op.execute(
        f"CREATE POLICY {table}_tenant_update ON {table} FOR UPDATE "
        f"USING ({update}) WITH CHECK ({update})"
    )
    op.execute(f"CREATE POLICY {table}_tenant_delete ON {table} FOR DELETE USING ({delete})")


def enable_tenant_rls(op, table: str, *, column: str = "company_id") -> None:
    """Strict tenant isolation. No escape hatch, by design."""
    scope = f"{column} = app.current_company_id()"
    _policies(op, table, select=scope, insert=scope, update=scope, delete=scope)


def enable_platform_tenant_rls(op, table: str, *, column: str = "company_id") -> None:
    """Tenant isolation, plus cross-tenant access for the platform operator."""
    scope = f"({column} = app.current_company_id() OR {_ADMIN})"
    _policies(op, table, select=scope, insert=scope, update=scope, delete=scope)


def enable_catalog_rls(op, table: str) -> None:
    """A global catalogue: everyone reads, only the platform writes."""
    _policies(op, table, select="true", insert=_ADMIN, update=_ADMIN, delete=_ADMIN)


def disable_tenant_rls(op, table: str) -> None:
    for action in ("select", "insert", "update", "delete"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_{action} ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
