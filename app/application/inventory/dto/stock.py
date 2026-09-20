import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.inventory.entities.stock_movement import MovementType, ReferenceType
from app.domain.shared.pagination import MAX_PAGE_SIZE


class AdjustStockCommand(BaseModel):
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    # Signed: negative writes stock off (breakage, shrinkage), positive adds it
    # back (a recount that found more than the system knew about).
    quantity_delta: Decimal = Field(max_digits=18, decimal_places=4)
    notes: str | None = Field(default=None, max_length=500)


class TransferStockCommand(BaseModel):
    product_id: uuid.UUID
    source_warehouse_id: uuid.UUID
    destination_warehouse_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    notes: str | None = Field(default=None, max_length=500)


class ListStockQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    product_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    only_non_zero: bool = False


class ListMovementsQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    product_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    reference_id: uuid.UUID | None = None


class ProductStockDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: Decimal
    updated_at: datetime


class StockMovementDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    movement_type: MovementType
    quantity: Decimal
    reference_type: ReferenceType
    reference_id: uuid.UUID | None
    notes: str | None
    created_by: uuid.UUID | None
    created_at: datetime


class StockPageDTO(BaseModel):
    items: list[ProductStockDTO]
    total: int
    page: int
    size: int
    pages: int


class MovementPageDTO(BaseModel):
    items: list[StockMovementDTO]
    total: int
    page: int
    size: int
    pages: int


class TransferResultDTO(BaseModel):
    source: ProductStockDTO
    destination: ProductStockDTO
