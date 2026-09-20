import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.purchases.entities.purchase import PurchaseStatus
from app.infrastructure.database.base import (
    MONEY,
    QUANTITY,
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)


class PurchaseModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "purchases"

    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[PurchaseStatus] = mapped_column(
        enum_column(PurchaseStatus, "purchase_status"),
        nullable=False,
        default=PurchaseStatus.DRAFT,
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

    items: Mapped[list["PurchaseItemModel"]] = relationship(
        back_populates="purchase",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PurchaseItemModel.created_at",
    )

    __table_args__ = (
        Index("ix_purchases_company_id_created_at", "company_id", "created_at"),
        Index("ix_purchases_company_id_status", "company_id", "status"),
        Index("ix_purchases_company_id_supplier_id", "company_id", "supplier_id"),
    )


class PurchaseItemModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "purchase_items"

    purchase_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    tax: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )
    total: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal("0"), server_default="0"
    )

    purchase: Mapped[PurchaseModel] = relationship(back_populates="items")

    __table_args__ = (
        Index("ix_purchase_items_purchase_id", "purchase_id"),
        Index("ix_purchase_items_company_id_product_id", "company_id", "product_id"),
    )
