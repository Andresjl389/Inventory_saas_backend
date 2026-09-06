import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.shared.pagination import MAX_PAGE_SIZE


class CreateProductCommand(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str = Field(min_length=1, max_length=64)
    description: str | None = None
    barcode: str | None = Field(default=None, max_length=64)
    category_id: uuid.UUID | None = None
    cost_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    sale_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)


class UpdateProductCommand(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    barcode: str | None = Field(default=None, max_length=64)
    category_id: uuid.UUID | None = None
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    is_active: bool | None = None


class ListProductsQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    search: str | None = None
    category_id: uuid.UUID | None = None
    is_active: bool | None = None


class ProductDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    description: str | None
    sku: str
    barcode: str | None
    cost_price: Decimal
    sale_price: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductPageDTO(BaseModel):
    items: list[ProductDTO]
    total: int
    page: int
    size: int
    pages: int
