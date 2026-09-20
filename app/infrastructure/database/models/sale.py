import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.sales.entities.sale import SaleStatus
from app.infrastructure.database.base import (
    MONEY,
    QUANTITY,
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)


class SaleModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "sales"

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[SaleStatus] = mapped_column(
        enum_column(SaleStatus, "sale_status"),
        nullable=False,
        default=SaleStatus.DRAFT,
        server_default="DRAFT",
    )
    subtotal: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    discount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    tax: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    total: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    items: Mapped[list["SaleItemModel"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="SaleItemModel.created_at",
    )

    __table_args__ = (
        Index("ix_sales_company_id_created_at", "company_id", "created_at"),
        Index("ix_sales_company_id_status", "company_id", "status"),
        Index("ix_sales_company_id_customer_id", "company_id", "customer_id"),
    )


class SaleItemModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    # company_id is denormalised onto the item so the line rows carry the same
    # RLS policies as everything else. BACKEND.md sketches sale_items without
    # it, but section 22 asks for RLS on every tenant-owned table and a policy
    # needs a company_id to compare against.
    __tablename__ = "sale_items"

    sale_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    tax: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    total: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )

    sale: Mapped[SaleModel] = relationship(back_populates="items")

    __table_args__ = (
        Index("ix_sale_items_sale_id", "sale_id"),
        Index("ix_sale_items_company_id_product_id", "company_id", "product_id"),
    )
