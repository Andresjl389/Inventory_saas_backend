import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

# 4 decimal places keeps unit prices exact for per-unit costs that are cents
# fractions; totals are rounded at the sale/purchase level.
MONEY = Numeric(18, 4)


class CategoryModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("company_id", "name"),)


class ProductModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "products"

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cost_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    sale_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("company_id", "sku"),
        # Partial unique index: many products may have no barcode.
        Index(
            "uq_products_company_id_barcode",
            "company_id",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
        ),
        Index("ix_products_company_id_is_active", "company_id", "is_active"),
        Index("ix_products_company_id_category_id", "company_id", "category_id"),
    )
