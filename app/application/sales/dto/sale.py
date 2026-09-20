import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.sales.entities.sale import SaleStatus
from app.domain.shared.pagination import MAX_PAGE_SIZE


class SaleItemCommand(BaseModel):
    product_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    # Left out, the product's current sale_price is used. Sent explicitly, it
    # wins -- that is how a negotiated price or a price list override works.
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    tax: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)


class CreateSaleCommand(BaseModel):
    warehouse_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    items: list[SaleItemCommand] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)
    # True runs creation and completion in the same transaction, which is the
    # point-of-sale case described in BACKEND.md section 28.
    complete: bool = False


class ListSalesQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    status: SaleStatus | None = None
    customer_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None


class SaleItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal


class SaleDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    customer_id: uuid.UUID | None
    warehouse_id: uuid.UUID
    status: SaleStatus
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    notes: str | None
    created_by: uuid.UUID | None
    items: list[SaleItemDTO]
    created_at: datetime
    updated_at: datetime


class SalePageDTO(BaseModel):
    items: list[SaleDTO]
    total: int
    page: int
    size: int
    pages: int
