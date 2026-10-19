import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.credit.entities.account import EntryType
from app.infrastructure.database.base import (
    MONEY,
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)


class AccountEntryModel(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Libro del fiado. Append-only: no se modifica ni se borra."""

    __tablename__ = "customer_account_entries"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    entry_type: Mapped[EntryType] = mapped_column(
        enum_column(EntryType, "account_entry_type"), nullable=False
    )
    # Con signo: la suma sobre un cliente es su saldo.
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # La venta o el abono que lo originó. Sin foreign key porque apunta a
    # tablas distintas según el tipo.
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_customer_account_entries_company_id_customer_id_created_at",
            "company_id",
            "customer_id",
            "created_at",
        ),
        Index("ix_customer_account_entries_company_id_reference_id", "company_id", "reference_id"),
    )


class CustomerBalanceModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Saldo actual por cliente. Caché del libro de arriba."""

    __tablename__ = "customer_balances"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    balance: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )

    __table_args__ = (
        # El upsert de lock_balance apunta a esta restricción.
        UniqueConstraint("company_id", "customer_id"),
    )
