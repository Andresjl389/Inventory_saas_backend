"""Only a platform administrator may create a company.

Sign-up used to accept a company *name* and create a tenant from it, so every
typo became a company and nobody could tell which of them was real. Companies
are now provisioned by an operator who names the owner at the same time, and
the INSERT policy is narrowed to match: the application rule and the database
rule say the same thing, so a future endpoint cannot quietly reopen the door.

Joining a company is unaffected -- that is a `company_members` row against a
company that already exists, and its own policy still lets a company's
administrators manage their team.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS companies_tenant_insert ON companies")
    op.execute(
        """
        CREATE POLICY companies_tenant_insert ON companies
        FOR INSERT
        WITH CHECK (app.is_platform_admin())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS companies_tenant_insert ON companies")
    op.execute(
        """
        CREATE POLICY companies_tenant_insert ON companies
        FOR INSERT
        WITH CHECK (id = app.current_company_id() OR app.is_platform_admin())
        """
    )
