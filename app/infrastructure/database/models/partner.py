"""Customers and suppliers.

They carry the same shape today, but they are separate tables on purpose: the
two will diverge (credit terms on one side, lead times and payment terms on the
other), and merging them now would make that split a migration.
"""

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.shared.document import DocumentType
from app.infrastructure.database.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)


class _PartyColumns:
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    document_type: Mapped[DocumentType | None] = mapped_column(
        enum_column(DocumentType, "document_type"), nullable=True
    )
    document_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )


class CustomerModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, _PartyColumns, Base):
    __tablename__ = "customers"

    __table_args__ = (
        UniqueConstraint("company_id", "document_type", "document_number"),
        Index("ix_customers_company_id_is_active", "company_id", "is_active"),
        Index("ix_customers_company_id_name", "company_id", "name"),
    )


class SupplierModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, _PartyColumns, Base):
    __tablename__ = "suppliers"

    __table_args__ = (
        UniqueConstraint("company_id", "document_type", "document_number"),
        Index("ix_suppliers_company_id_is_active", "company_id", "is_active"),
        Index("ix_suppliers_company_id_name", "company_id", "name"),
    )
