"""Escaneo de facturas: leer el papel del proveedor y volverlo una compra.

Dos tablas con la misma forma que un import: el escaneo es el trabajo y los
renglones son lo que hay que revisar. La diferencia con el import es de dónde
salen los datos -- una foto, leída por un modelo -- y por eso la decisión de
cada renglón es una columna (`action`), no una suposición.

La restricción `product_matches_action` es el corazón del módulo puesto en la
base: un renglón enlazado dice a qué producto, y uno que no está enlazado no
arrastra un producto suelto. Así ni un bug de la aplicación puede meter al
inventario mercancía que nadie revisó.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.domain.invoices.entities.scan import LineAction, ScanStatus
from app.infrastructure.database.migration_helpers import (
    enum_column,
    money_column,
    quantity_column,
    timestamps,
    uuid_column,
    uuid_pk,
)
from app.infrastructure.database.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCAN_STATUSES = tuple(item.value for item in ScanStatus)
LINE_ACTIONS = tuple(item.value for item in LineAction)

# Confianza: NUMERIC como el dinero, nunca FLOAT.
CONFIDENCE = sa.Numeric(5, 4)

INVOICE_PERMISSIONS = (
    ("invoices.read", "invoices", "Ver facturas escaneadas"),
    ("invoices.scan", "invoices", "Escanear facturas y convertirlas en compras"),
)
INVOICE_GRANTS = {
    "ADMIN": ("invoices.read", "invoices.scan"),
    # Quien recibe la mercancía es quien escanea la factura.
    "INVENTORY_MANAGER": ("invoices.read", "invoices.scan"),
    # El vendedor ve lo que llegó; crear compras no es lo suyo.
    "SELLER": ("invoices.read",),
}


def upgrade() -> None:
    op.create_table(
        "invoice_scans",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("file_id"),
        sa.Column("filename", sa.String(255), nullable=False),
        enum_column(
            "status",
            SCAN_STATUSES,
            "invoice_scan_status",
            nullable=False,
            server_default=ScanStatus.EXTRACTED.value,
        ),
        # Lo que decía el papel, y a quién terminó apuntando.
        sa.Column("supplier_name", sa.String(200), nullable=True),
        sa.Column("supplier_tax_id", sa.String(64), nullable=True),
        uuid_column("supplier_id", nullable=True),
        uuid_column("warehouse_id", nullable=True),
        sa.Column("invoice_number", sa.String(64), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        money_column("declared_subtotal", default=None, nullable=True),
        money_column("declared_tax", default=None, nullable=True),
        money_column("declared_total", default=None, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "extraction",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        uuid_column("purchase_id", nullable=True),
        uuid_column("created_by", nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_scans"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_invoice_scans_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name="fk_invoice_scans_file_id_files", ondelete="CASCADE"
        ),
        # RESTRICT: un proveedor o una bodega con historial se desactivan, no
        # se borran.
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_invoice_scans_supplier_id_suppliers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_invoice_scans_warehouse_id_warehouses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_id"],
            ["purchases.id"],
            name="fk_invoice_scans_purchase_id_purchases",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_invoice_scans_created_by_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_invoice_scans_company_id", "invoice_scans", ["company_id"])
    op.create_index(
        "ix_invoice_scans_company_id_created_at", "invoice_scans", ["company_id", "created_at"]
    )
    op.create_index("ix_invoice_scans_company_id_status", "invoice_scans", ["company_id", "status"])

    op.create_table(
        "invoice_scan_lines",
        uuid_pk(),
        uuid_column("company_id"),
        uuid_column("scan_id"),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        quantity_column("quantity"),
        money_column("unit_cost", default=None),
        money_column("discount"),
        money_column("tax"),
        # NULL no es cero: es "el renglón no traía total impreso", y la
        # diferencia es lo que delata una lectura mala.
        money_column("declared_total", default=None, nullable=True),
        sa.Column("confidence", CONFIDENCE, nullable=False, server_default="1"),
        uuid_column("suggested_product_id", nullable=True),
        sa.Column("match_confidence", CONFIDENCE, nullable=False, server_default="0"),
        sa.Column("match_reason", sa.String(32), nullable=False, server_default="unmatched"),
        enum_column(
            "action",
            LINE_ACTIONS,
            "invoice_line_action",
            nullable=False,
            server_default=LineAction.PENDING.value,
        ),
        uuid_column("product_id", nullable=True),
        sa.Column(
            "new_product",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "warnings",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_scan_lines"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_invoice_scan_lines_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"],
            ["invoice_scans.id"],
            name="fk_invoice_scan_lines_scan_id_invoice_scans",
            ondelete="CASCADE",
        ),
        # La sugerencia se puede quedar sin producto (SET NULL); la decisión no
        # (RESTRICT), porque un renglón enlazado es una compra por hacer.
        sa.ForeignKeyConstraint(
            ["suggested_product_id"],
            ["products.id"],
            name="fk_invoice_scan_lines_suggested_product_id_products",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_invoice_scan_lines_product_id_products",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint(
            "unit_cost >= 0 AND discount >= 0 AND tax >= 0", name="amounts_non_negative"
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1 AND match_confidence BETWEEN 0 AND 1",
            name="confidence_within_range",
        ),
        sa.CheckConstraint(
            "(action = 'LINK') = (product_id IS NOT NULL)", name="product_matches_action"
        ),
    )
    op.create_index("ix_invoice_scan_lines_company_id", "invoice_scan_lines", ["company_id"])
    # Único: dos renglones no pueden pelearse el mismo número dentro de una
    # factura, o la revisión deja de poder seguirse con el papel al lado.
    op.create_index(
        "uq_invoice_scan_lines_scan_id_line_number",
        "invoice_scan_lines",
        ["scan_id", "line_number"],
        unique=True,
    )
    op.create_index(
        "ix_invoice_scan_lines_company_id_product_id",
        "invoice_scan_lines",
        ["company_id", "product_id"],
    )

    enable_tenant_rls(op, "invoice_scans")
    enable_tenant_rls(op, "invoice_scan_lines")

    _seed_invoice_permissions()


def _seed_invoice_permissions() -> None:
    # Una migración es una operación de plataforma; SET LOCAL deja el flag en
    # esta transacción. Idempotente porque una base nueva ya recibe estos
    # códigos en 0008, que siembra el catálogo entero.
    op.execute("SET LOCAL app.is_platform_admin = 'true'")

    for code, module, description in INVOICE_PERMISSIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO permissions (code, module, description)
                VALUES (:code, :module, :description)
                ON CONFLICT (code) DO NOTHING
                """
            ).bindparams(code=code, module=module, description=description)
        )

    for role_code, codes in INVOICE_GRANTS.items():
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
    disable_tenant_rls(op, "invoice_scan_lines")
    disable_tenant_rls(op, "invoice_scans")
    op.drop_table("invoice_scan_lines")
    op.drop_table("invoice_scans")

    op.execute("SET LOCAL app.is_platform_admin = 'true'")
    op.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)").bindparams(
            codes=[code for code, _, _ in INVOICE_PERMISSIONS]
        )
    )
