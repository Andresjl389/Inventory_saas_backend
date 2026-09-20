import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.inventory.entities.stock_movement import MovementType, ReferenceType
from app.infrastructure.database.base import (
    QUANTITY,
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)


class WarehouseModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "warehouses"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    __table_args__ = (
        UniqueConstraint("company_id", "name"),
        Index("ix_warehouses_company_id_is_active", "company_id", "is_active"),
    )


class ProductStockModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Current stock per (product, warehouse). Read path for every stock query."""

    __tablename__ = "product_stock"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(
        QUANTITY, nullable=False, default=Decimal("0"), server_default="0"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "product_id", "warehouse_id"),
        Index("ix_product_stock_company_id_warehouse_id", "company_id", "warehouse_id"),
    )


class StockMovementModel(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Append-only ledger. No updated_at: a movement is never modified."""

    __tablename__ = "stock_movements"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    movement_type: Mapped[MovementType] = mapped_column(
        enum_column(MovementType, "movement_type"), nullable=False
    )
    # Signed delta: the sum over a (product, warehouse) equals product_stock.
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    reference_type: Mapped[ReferenceType] = mapped_column(
        enum_column(ReferenceType, "reference_type"),
        nullable=False,
        default=ReferenceType.MANUAL,
        server_default=ReferenceType.MANUAL.value,
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_stock_movements_company_id_created_at", "company_id", "created_at"),
        Index(
            "ix_stock_movements_company_id_product_id_warehouse_id",
            "company_id",
            "product_id",
            "warehouse_id",
        ),
        Index("ix_stock_movements_company_id_reference_id", "company_id", "reference_id"),
    )
