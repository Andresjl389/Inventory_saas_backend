from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.audit.dto.audit import AuditPageDTO, ListAuditQuery
from app.application.audit.use_cases.read_audit_log import ReadAuditLogUseCase
from app.application.reports.dto.reports import (
    InventoryValuationDTO,
    LowStockReportDTO,
    ReportPeriodQuery,
    SalesReportDTO,
)
from app.application.reports.use_cases.report_use_cases import (
    InventoryValuationUseCase,
    LowStockReportUseCase,
    SalesReportUseCase,
)
from app.domain.audit.entities.audit_entry import AuditAction
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import AuditRepoDep, ReportRepoDep
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/reports", tags=["reports"])

ReadDep = Annotated[TenantContext, Depends(require_permission("reports.read"))]
AuditDep = Annotated[TenantContext, Depends(require_permission("audit.read"))]


@router.get("/sales", response_model=SalesReportDTO)
async def sales_report(
    tenant: ReadDep,
    reports: ReportRepoDep,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> SalesReportDTO:
    """Revenue and best sellers for a period. Only COMPLETED sales count."""
    query = ReportPeriodQuery(since=since, until=until, limit=limit)
    return await SalesReportUseCase(reports).execute(query, tenant=tenant)


@router.get("/inventory-valuation", response_model=InventoryValuationDTO)
async def inventory_valuation(tenant: ReadDep, reports: ReportRepoDep) -> InventoryValuationDTO:
    """What the stock on hand is worth, per warehouse, at cost and at retail."""
    return await InventoryValuationUseCase(reports).execute(tenant=tenant)


@router.get("/low-stock", response_model=LowStockReportDTO)
async def low_stock(
    tenant: ReadDep,
    reports: ReportRepoDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> LowStockReportDTO:
    """Products at or below their reorder threshold. Same query the nightly
    low-stock job runs."""
    return await LowStockReportUseCase(reports).execute(tenant=tenant, limit=limit)


@router.get("/audit", response_model=AuditPageDTO)
async def audit_log(
    tenant: AuditDep,
    audit: AuditRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    action: AuditAction | None = None,
) -> AuditPageDTO:
    """This company's audit trail. Platform-level events are not in here."""
    query = ListAuditQuery(page=page, size=size, action=action)
    return await ReadAuditLogUseCase(audit).execute(query, tenant=tenant)
