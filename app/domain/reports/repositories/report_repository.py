"""Read-side port for reporting.

Reports are aggregations, not entities: forcing them through the entity
repositories would mean loading thousands of rows to add them up in Python.
This port returns plain records, and the SQL lives in the adapter.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SalesSummary:
    sales_count: int
    revenue: Decimal
    discount: Decimal
    tax: Decimal
    average_ticket: Decimal


@dataclass(frozen=True, slots=True)
class ProductSales:
    product_id: uuid.UUID
    product_name: str
    sku: str
    quantity: Decimal
    revenue: Decimal


@dataclass(frozen=True, slots=True)
class WarehouseValuation:
    warehouse_id: uuid.UUID
    warehouse_name: str
    units: Decimal
    cost_value: Decimal
    retail_value: Decimal


@dataclass(frozen=True, slots=True)
class LowStockRow:
    product_id: uuid.UUID
    product_name: str
    sku: str
    warehouse_id: uuid.UUID | None
    warehouse_name: str | None
    quantity: Decimal
    min_stock: Decimal


class ReportRepository(Protocol):
    async def sales_summary(
        self, company_id: uuid.UUID, *, since: datetime | None, until: datetime | None
    ) -> SalesSummary: ...

    async def top_products(
        self,
        company_id: uuid.UUID,
        *,
        since: datetime | None,
        until: datetime | None,
        limit: int,
    ) -> list[ProductSales]: ...

    async def inventory_valuation(self, company_id: uuid.UUID) -> list[WarehouseValuation]: ...

    async def low_stock(self, company_id: uuid.UUID, *, limit: int) -> list[LowStockRow]: ...
