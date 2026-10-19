"""Fiado: el libro de la cuenta de cada cliente y su saldo.

Mismo patron que el inventario, y por la misma razon: el saldo no es un numero
que alguien edita, es la suma de un libro append-only. Asi cada peso que un
cliente debe se puede explicar con la venta o el abono que lo movio.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.domain.credit.entities.account import EntryType, PaymentMethod
from app.infrastructure.database.migration_helpers import (
    enum_column,
    money_column,
    timestamps,
    uuid_column,
    uuid_pk,
)
from app.infrastructure.database.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENTRY_TYPES = tuple(item.value for item in EntryType)
PAYMENT_METHODS = tuple(item.value for item in PaymentMethod)

CREDIT_PERMISSIONS = (
    ("credit.read", "credit", "Ver saldos de fiado"),
    ("credit.manage", "credit", "Registrar abonos y ajustar cuentas"),
)
CREDIT_GRANTS = {
    "ADMIN": ("credit.read", "credit.manage"),
    "INVENTORY_MANAGER": ("credit.read",),
    # El vendedor fia y recibe abonos: es el mostrador.
    "SELLER": ("credit.read", "credit.manage"),
}


def upgrade() -> None:
    op.add_column(
        "sales",
        enum_column(
            "payment_method",
            PAYMENT_METHODS,
            "payment_method",
            nullable=False,
            server_default="CASH",
        ),
    )
    op.add_column("sales", money_column("amount_paid"))
    op.create_check_constraint(
        "amount_paid_within_total", "sales", "amount_paid >= 0 AND amount_paid <= total"
    )

    # Tope de fiado por cliente. 0 = sin tope.
    op.add_column("customers", money_column("credit_limit"))
    op.create_check_constraint("credit_limit_non_negative", "customers", "credit_limit >= 0")

    op.create_table(
        "customer_account_entries",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("customer_id"),
        enum_column("entry_type", ENTRY_TYPES, "account_entry_type", nullable=False),
        # Con signo: la suma sobre un cliente es su saldo.
        money_column("amount", default=None),
        uuid_column("reference_id", nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        uuid_column("created_by", nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_customer_account_entries"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_customer_account_entries_company_id_companies",
            ondelete="CASCADE",
        ),
        # RESTRICT: un cliente con historial de fiado se desactiva, no se borra.
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_customer_account_entries_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_customer_account_entries_created_by_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("amount <> 0", name="amount_not_zero"),
        # El signo tiene que concordar con el tipo, o el libro deja de
        # reconstruir el saldo de forma fiable.
        sa.CheckConstraint(
            """
            (entry_type = 'SALE' AND amount > 0)
            OR (entry_type IN ('PAYMENT', 'SALE_REVERSED') AND amount < 0)
            OR entry_type = 'ADJUSTMENT'
            """,
            name="amount_sign_matches_type",
        ),
    )
    op.create_index(
        "ix_customer_account_entries_company_id", "customer_account_entries", ["company_id"]
    )
    op.create_index(
        "ix_customer_account_entries_company_id_customer_id_created_at",
        "customer_account_entries",
        ["company_id", "customer_id", "created_at"],
    )
    op.create_index(
        "ix_customer_account_entries_company_id_reference_id",
        "customer_account_entries",
        ["company_id", "reference_id"],
    )

    op.create_table(
        "customer_balances",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("customer_id"),
        money_column("balance"),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_balances"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_customer_balances_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_customer_balances_customer_id_customers",
            ondelete="CASCADE",
        ),
        # El upsert de lock_balance apunta a esta restriccion.
        sa.UniqueConstraint(
            "company_id", "customer_id", name="uq_customer_balances_company_id_customer_id"
        ),
    )
    op.create_index("ix_customer_balances_company_id", "customer_balances", ["company_id"])

    enable_tenant_rls(op, "customer_account_entries")
    enable_tenant_rls(op, "customer_balances")

    # El libro es append-only: sin UPDATE ni DELETE para nadie.
    op.execute(
        "DROP POLICY IF EXISTS customer_account_entries_tenant_update ON customer_account_entries"
    )
    op.execute(
        "DROP POLICY IF EXISTS customer_account_entries_tenant_delete ON customer_account_entries"
    )

    _seed_credit_permissions()


def _seed_credit_permissions() -> None:
    # Una migracion es una operacion de plataforma; SET LOCAL deja el flag en
    # esta transaccion. Idempotente porque una base nueva ya recibe estos
    # codigos en 0008, que siembra el catalogo entero.
    op.execute("SET LOCAL app.is_platform_admin = 'true'")

    for code, module, description in CREDIT_PERMISSIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO permissions (code, module, description)
                VALUES (:code, :module, :description)
                ON CONFLICT (code) DO NOTHING
                """
            ).bindparams(code=code, module=module, description=description)
        )

    for role_code, codes in CREDIT_GRANTS.items():
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
    disable_tenant_rls(op, "customer_balances")
    disable_tenant_rls(op, "customer_account_entries")
    op.drop_table("customer_balances")
    op.drop_table("customer_account_entries")

    # create_check_constraint y drop_constraint aplican los dos la convención de
    # nombres, así que ambos reciben el sufijo, no el nombre completo.
    op.drop_constraint("credit_limit_non_negative", "customers", type_="check")
    op.drop_column("customers", "credit_limit")
    op.drop_constraint("amount_paid_within_total", "sales", type_="check")
    op.drop_column("sales", "amount_paid")
    op.drop_column("sales", "payment_method")

    op.execute("SET LOCAL app.is_platform_admin = 'true'")
    op.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(
            codes=[code for code, _, _ in CREDIT_PERMISSIONS]
        )
    )
