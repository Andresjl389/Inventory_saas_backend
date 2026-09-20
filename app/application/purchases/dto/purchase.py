import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.purchases.entities.purchase import PurchaseStatus
from app.domain.shared.pagination import MAX_PAGE_SIZE


class PurchaseItemCommand(BaseModel):
    product_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    tax: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)


class CreatePurchaseCommand(BaseModel):
    warehouse_id: uuid.UUID
    supplier_id: uuid.UUID | None = None
    items: list[PurchaseItemCommand] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)
    complete: bool = False
    # Completing a purchase can refresh each product's cost_price with what was
    # actually paid. Off by default: many businesses want a weighted average
    # instead of last-cost, and that is a decision, not a default.
    update_product_costs: bool = False


class ListPurchasesQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    status: PurchaseStatus | None = None
    supplier_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None


class PurchaseItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal
    unit_cost: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal


class PurchaseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    supplier_id: uuid.UUID | None
    warehouse_id: uuid.UUID
    status: PurchaseStatus
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    notes: str | None
    created_by: uuid.UUID | None
    items: list[PurchaseItemDTO]
    created_at: datetime
    updated_at: datetime


class PurchasePageDTO(BaseModel):
    items: list[PurchaseDTO]
    total: int
    page: int
    size: int
    pages: int
