from decimal import Decimal

from app.application.reports.dto.reports import (
    InventoryValuationDTO,
    LowStockReportDTO,
    LowStockRowDTO,
    ProductSalesDTO,
    ReportPeriodQuery,
    SalesReportDTO,
    SalesSummaryDTO,
    WarehouseValuationDTO,
)
from app.domain.reports.repositories.report_repository import ReportRepository
from app.domain.tenants.tenant_context import TenantContext

ZERO = Decimal("0")


class SalesReportUseCase:
    def __init__(self, reports: ReportRepository) -> None:
        self._reports = reports

    async def execute(self, query: ReportPeriodQuery, *, tenant: TenantContext) -> SalesReportDTO:
        summary = await self._reports.sales_summary(
            tenant.company_id, since=query.since, until=query.until
        )
        top = await self._reports.top_products(
            tenant.company_id, since=query.since, until=query.until, limit=query.limit
        )
        return SalesReportDTO(
            since=query.since,
            until=query.until,
            summary=SalesSummaryDTO.model_validate(summary, from_attributes=True),
            top_products=[ProductSalesDTO.model_validate(row, from_attributes=True) for row in top],
        )


class InventoryValuationUseCase:
    """What the stock on hand is worth, at cost and at retail."""

    def __init__(self, reports: ReportRepository) -> None:
        self._reports = reports

    async def execute(self, *, tenant: TenantContext) -> InventoryValuationDTO:
        rows = await self._reports.inventory_valuation(tenant.company_id)
        warehouses = [
            WarehouseValuationDTO.model_validate(row, from_attributes=True) for row in rows
        ]
        return InventoryValuationDTO(
            warehouses=warehouses,
            total_units=sum((w.units for w in warehouses), ZERO),
            total_cost_value=sum((w.cost_value for w in warehouses), ZERO),
            total_retail_value=sum((w.retail_value for w in warehouses), ZERO),
        )


class LowStockReportUseCase:
    def __init__(self, reports: ReportRepository) -> None:
        self._reports = reports

    async def execute(self, *, tenant: TenantContext, limit: int = 50) -> LowStockReportDTO:
        rows = await self._reports.low_stock(tenant.company_id, limit=limit)
        items = [LowStockRowDTO.model_validate(row, from_attributes=True) for row in rows]
        return LowStockReportDTO(items=items, total=len(items))
