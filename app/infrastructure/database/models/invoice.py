import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy import text as sql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.invoices.entities.scan import LineAction, ScanStatus
from app.infrastructure.database.base import (
    MONEY,
    QUANTITY,
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)

# La confianza es un número entre 0 y 1 con cuatro decimales: NUMERIC, no
# FLOAT, por la misma razón que el dinero (BACKEND.md sección 12).
CONFIDENCE = Numeric(5, 4)


class InvoiceScanModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "invoice_scans"

    file_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ScanStatus] = mapped_column(
        enum_column(ScanStatus, "invoice_scan_status"),
        nullable=False,
        default=ScanStatus.EXTRACTED,
        server_default=ScanStatus.EXTRACTED.value,
    )

    supplier_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    supplier_tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # RESTRICT como en las compras: un proveedor con historial se desactiva.
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True
    )

    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    declared_subtotal: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    declared_tax: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    declared_total: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Quién la leyó, con qué modelo y qué avisó.
    extraction: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sql("'{}'::jsonb")
    )

    purchase_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    lines: Mapped[list["InvoiceScanLineModel"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="InvoiceScanLineModel.line_number",
    )

    __table_args__ = (
        Index("ix_invoice_scans_company_id_created_at", "company_id", "created_at"),
        Index("ix_invoice_scans_company_id_status", "company_id", "status"),
    )


class InvoiceScanLineModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "invoice_scan_lines"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("invoice_scans.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    tax: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    # El total impreso en el papel, cuando lo trae. NULL no es cero: es "el
    # renglón no decía", y la diferencia importa para detectar mala lectura.
    declared_total: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    confidence: Mapped[Decimal] = mapped_column(
        CONFIDENCE, nullable=False, default=Decimal("1"), server_default="1"
    )

    suggested_product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    match_confidence: Mapped[Decimal] = mapped_column(
        CONFIDENCE, nullable=False, default=Decimal("0"), server_default="0"
    )
    match_reason: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unmatched", server_default="unmatched"
    )

    action: Mapped[LineAction] = mapped_column(
        enum_column(LineAction, "invoice_line_action"),
        nullable=False,
        default=LineAction.PENDING,
        server_default=LineAction.PENDING.value,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )
    new_product: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sql("'{}'::jsonb")
    )
    warnings: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql("'[]'::jsonb")
    )

    scan: Mapped[InvoiceScanModel] = relationship(back_populates="lines")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "unit_cost >= 0 AND discount >= 0 AND tax >= 0", name="amounts_non_negative"
        ),
        CheckConstraint(
            "confidence BETWEEN 0 AND 1 AND match_confidence BETWEEN 0 AND 1",
            name="confidence_within_range",
        ),
        # La invariante del módulo, en la base: un renglón enlazado dice a qué
        # producto, y uno que no está enlazado no arrastra un producto suelto.
        CheckConstraint(
            "(action = 'LINK') = (product_id IS NOT NULL)",
            name="product_matches_action",
        ),
        Index(
            "uq_invoice_scan_lines_scan_id_line_number",
            "scan_id",
            "line_number",
            unique=True,
        ),
        Index("ix_invoice_scan_lines_company_id_product_id", "company_id", "product_id"),
    )
