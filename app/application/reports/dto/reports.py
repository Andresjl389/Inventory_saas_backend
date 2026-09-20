import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ReportPeriodQuery(BaseModel):
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=10, ge=1, le=100)


class SalesSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sales_count: int
    revenue: Decimal
    discount: Decimal
    tax: Decimal
    average_ticket: Decimal


class ProductSalesDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID
    product_name: str
    sku: str
    quantity: Decimal
    revenue: Decimal


class SalesReportDTO(BaseModel):
    since: datetime | None
    until: datetime | None
    summary: SalesSummaryDTO
    top_products: list[ProductSalesDTO]


class WarehouseValuationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    warehouse_id: uuid.UUID
    warehouse_name: str
    units: Decimal
    cost_value: Decimal
    retail_value: Decimal


class InventoryValuationDTO(BaseModel):
    warehouses: list[WarehouseValuationDTO]
    total_units: Decimal
    total_cost_value: Decimal
    total_retail_value: Decimal


class LowStockRowDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID
    product_name: str
    sku: str
    warehouse_id: uuid.UUID | None
    warehouse_name: str | None
    quantity: Decimal
    min_stock: Decimal


class LowStockReportDTO(BaseModel):
    items: list[LowStockRowDTO]
    total: int
