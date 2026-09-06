"""Extensions, app schema and tenant-context functions.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # gen_random_uuid() needs pgcrypto on PostgreSQL < 13 (built in from 13).
    # Creating an extension requires superuser, and the application role
    # deliberately is not one -- so only attempt it when it is missing, which
    # lets `alembic upgrade head` run as the unprivileged app role against a
    # database whose extensions were provisioned by the DBA (see
    # docker/postgres/init.sql).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto') THEN
                CREATE EXTENSION pgcrypto;
            END IF;
        END
        $$;
        """
    )

    op.execute("CREATE SCHEMA IF NOT EXISTS app")

    # Every RLS policy reads the request's tenant through this function.
    # `current_setting(..., true)` returns NULL when unset, and NULL never
    # equals a company_id -- so an unscoped transaction sees nothing.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.current_company_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        AS $$
            SELECT NULLIF(current_setting('app.current_company_id', true), '')::uuid;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.current_user_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        AS $$
            SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid;
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.current_user_id()")
    op.execute("DROP FUNCTION IF EXISTS app.current_company_id()")
    op.execute("DROP SCHEMA IF EXISTS app")
