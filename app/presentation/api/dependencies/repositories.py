"""Composition root for repositories.

Use cases depend on the domain Protocols; the concrete SQLAlchemy classes are
only ever named here.
"""

from typing import Annotated

from fastapi import Depends

from app.application.audit.services.audit_service import AuditService
from app.application.credit.services.credit_service import CreditService
from app.application.inventory.services.stock_service import StockService
from app.domain.files.storage import FileStorage
from app.domain.imports.table import SpreadsheetReader
from app.domain.invoices.extraction import InvoiceExtractor
from app.infrastructure.database.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.database.repositories.billing_repository import (
    SqlAlchemyPlanRepository,
    SqlAlchemySubscriptionRepository,
)
from app.infrastructure.database.repositories.category_repository import (
    SqlAlchemyCategoryRepository,
)
from app.infrastructure.database.repositories.company_member_repository import (
    SqlAlchemyCompanyMemberRepository,
)
from app.infrastructure.database.repositories.company_overview_repository import (
    SqlAlchemyCompanyOverviewRepository,
)
from app.infrastructure.database.repositories.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.repositories.credit_repository import SqlAlchemyCreditRepository
from app.infrastructure.database.repositories.file_repository import SqlAlchemyFileRepository
from app.infrastructure.database.repositories.import_repository import (
    SqlAlchemyImportJobRepository,
)
from app.infrastructure.database.repositories.invoice_repository import (
    SqlAlchemyInvoiceScanRepository,
)
from app.infrastructure.database.repositories.notification_repository import (
    SqlAlchemyNotificationRepository,
)
from app.infrastructure.database.repositories.partner_repository import (
    SqlAlchemyCustomerRepository,
    SqlAlchemySupplierRepository,
)
from app.infrastructure.database.repositories.platform_stats_repository import (
    SqlAlchemyPlatformStatsRepository,
)
from app.infrastructure.database.repositories.product_repository import SqlAlchemyProductRepository
from app.infrastructure.database.repositories.purchase_repository import (
    SqlAlchemyPurchaseRepository,
)
from app.infrastructure.database.repositories.report_repository import SqlAlchemyReportRepository
from app.infrastructure.database.repositories.role_repository import (
    SqlAlchemyPermissionRepository,
    SqlAlchemyRoleRepository,
)
from app.infrastructure.database.repositories.sale_repository import SqlAlchemySaleRepository
from app.infrastructure.database.repositories.stock_repository import (
    SqlAlchemyStockMovementRepository,
    SqlAlchemyStockRepository,
)
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.infrastructure.database.repositories.warehouse_repository import (
    SqlAlchemyWarehouseRepository,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.imports.reader import OpenpyxlSpreadsheetReader
from app.infrastructure.invoices.factory import get_invoice_extractor
from app.infrastructure.storage.factory import get_file_storage
from app.presentation.api.dependencies.database import SessionDep


def get_user_repository(session: SessionDep) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(session)


def get_company_repository(session: SessionDep) -> SqlAlchemyCompanyRepository:
    return SqlAlchemyCompanyRepository(session)


def get_company_member_repository(session: SessionDep) -> SqlAlchemyCompanyMemberRepository:
    return SqlAlchemyCompanyMemberRepository(session)


def get_category_repository(session: SessionDep) -> SqlAlchemyCategoryRepository:
    return SqlAlchemyCategoryRepository(session)


def get_product_repository(session: SessionDep) -> SqlAlchemyProductRepository:
    return SqlAlchemyProductRepository(session)


def get_warehouse_repository(session: SessionDep) -> SqlAlchemyWarehouseRepository:
    return SqlAlchemyWarehouseRepository(session)


def get_stock_repository(session: SessionDep) -> SqlAlchemyStockRepository:
    return SqlAlchemyStockRepository(session)


def get_stock_movement_repository(session: SessionDep) -> SqlAlchemyStockMovementRepository:
    return SqlAlchemyStockMovementRepository(session)


def get_customer_repository(session: SessionDep) -> SqlAlchemyCustomerRepository:
    return SqlAlchemyCustomerRepository(session)


def get_supplier_repository(session: SessionDep) -> SqlAlchemySupplierRepository:
    return SqlAlchemySupplierRepository(session)


def get_sale_repository(session: SessionDep) -> SqlAlchemySaleRepository:
    return SqlAlchemySaleRepository(session)


def get_purchase_repository(session: SessionDep) -> SqlAlchemyPurchaseRepository:
    return SqlAlchemyPurchaseRepository(session)


def get_role_repository(session: SessionDep) -> SqlAlchemyRoleRepository:
    return SqlAlchemyRoleRepository(session)


def get_permission_repository(session: SessionDep) -> SqlAlchemyPermissionRepository:
    return SqlAlchemyPermissionRepository(session)


def get_audit_repository(session: SessionDep) -> SqlAlchemyAuditRepository:
    return SqlAlchemyAuditRepository(session)


def get_plan_repository(session: SessionDep) -> SqlAlchemyPlanRepository:
    return SqlAlchemyPlanRepository(session)


def get_subscription_repository(session: SessionDep) -> SqlAlchemySubscriptionRepository:
    return SqlAlchemySubscriptionRepository(session)


def get_notification_repository(session: SessionDep) -> SqlAlchemyNotificationRepository:
    return SqlAlchemyNotificationRepository(session)


def get_file_repository(session: SessionDep) -> SqlAlchemyFileRepository:
    return SqlAlchemyFileRepository(session)


def get_company_overview_repository(session: SessionDep) -> SqlAlchemyCompanyOverviewRepository:
    return SqlAlchemyCompanyOverviewRepository(session)


def get_import_repository(session: SessionDep) -> SqlAlchemyImportJobRepository:
    return SqlAlchemyImportJobRepository(session)


def get_unit_of_work(session: SessionDep) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def get_loader_repositories(session: SessionDep) -> dict:
    """Everything the import loaders may need, wired once.

    A loader asks for what its entity requires; building them all costs a few
    object allocations and keeps the router from knowing which needs what.
    """
    return {
        "categories": SqlAlchemyCategoryRepository(session),
        "products": SqlAlchemyProductRepository(session),
        "warehouses": SqlAlchemyWarehouseRepository(session),
        "customers": SqlAlchemyCustomerRepository(session),
        "suppliers": SqlAlchemySupplierRepository(session),
        "stock": SqlAlchemyStockRepository(session),
        "stock_service": StockService(
            SqlAlchemyStockRepository(session), SqlAlchemyStockMovementRepository(session)
        ),
    }


def get_invoice_scan_repository(session: SessionDep) -> SqlAlchemyInvoiceScanRepository:
    return SqlAlchemyInvoiceScanRepository(session)


def get_extractor() -> InvoiceExtractor:
    """El lector de facturas. Cacheado, así que el cliente del modelo se arma
    una sola vez."""
    return get_invoice_extractor()


def get_spreadsheet_reader() -> SpreadsheetReader:
    return OpenpyxlSpreadsheetReader()


def get_storage() -> FileStorage:
    """The blob store. Cached, so the local adapter creates its root once."""
    return get_file_storage()


def get_report_repository(session: SessionDep) -> SqlAlchemyReportRepository:
    return SqlAlchemyReportRepository(session)


def get_platform_stats_repository(session: SessionDep) -> SqlAlchemyPlatformStatsRepository:
    return SqlAlchemyPlatformStatsRepository(session)


def get_audit_service(session: SessionDep) -> AuditService:
    return AuditService(SqlAlchemyAuditRepository(session))


def get_credit_repository(session: SessionDep) -> SqlAlchemyCreditRepository:
    return SqlAlchemyCreditRepository(session)


def get_credit_service(session: SessionDep) -> CreditService:
    """El único escritor de saldos de fiado: ventas, abonos y ajustes pasan
    todos por aquí."""
    return CreditService(SqlAlchemyCreditRepository(session))


def get_stock_service(session: SessionDep) -> StockService:
    """The only writer of product_stock; sales, purchases, transfers and manual
    adjustments all go through it."""
    return StockService(
        SqlAlchemyStockRepository(session), SqlAlchemyStockMovementRepository(session)
    )


UserRepoDep = Annotated[SqlAlchemyUserRepository, Depends(get_user_repository)]
CompanyRepoDep = Annotated[SqlAlchemyCompanyRepository, Depends(get_company_repository)]
MemberRepoDep = Annotated[SqlAlchemyCompanyMemberRepository, Depends(get_company_member_repository)]
CategoryRepoDep = Annotated[SqlAlchemyCategoryRepository, Depends(get_category_repository)]
ProductRepoDep = Annotated[SqlAlchemyProductRepository, Depends(get_product_repository)]
WarehouseRepoDep = Annotated[SqlAlchemyWarehouseRepository, Depends(get_warehouse_repository)]
StockRepoDep = Annotated[SqlAlchemyStockRepository, Depends(get_stock_repository)]
MovementRepoDep = Annotated[
    SqlAlchemyStockMovementRepository, Depends(get_stock_movement_repository)
]
CustomerRepoDep = Annotated[SqlAlchemyCustomerRepository, Depends(get_customer_repository)]
SupplierRepoDep = Annotated[SqlAlchemySupplierRepository, Depends(get_supplier_repository)]
SaleRepoDep = Annotated[SqlAlchemySaleRepository, Depends(get_sale_repository)]
PurchaseRepoDep = Annotated[SqlAlchemyPurchaseRepository, Depends(get_purchase_repository)]
StockServiceDep = Annotated[StockService, Depends(get_stock_service)]
RoleRepoDep = Annotated[SqlAlchemyRoleRepository, Depends(get_role_repository)]
PermissionRepoDep = Annotated[SqlAlchemyPermissionRepository, Depends(get_permission_repository)]
AuditRepoDep = Annotated[SqlAlchemyAuditRepository, Depends(get_audit_repository)]
PlanRepoDep = Annotated[SqlAlchemyPlanRepository, Depends(get_plan_repository)]
SubscriptionRepoDep = Annotated[
    SqlAlchemySubscriptionRepository, Depends(get_subscription_repository)
]
NotificationRepoDep = Annotated[
    SqlAlchemyNotificationRepository, Depends(get_notification_repository)
]
ReportRepoDep = Annotated[SqlAlchemyReportRepository, Depends(get_report_repository)]
PlatformStatsDep = Annotated[
    SqlAlchemyPlatformStatsRepository, Depends(get_platform_stats_repository)
]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
FileRepoDep = Annotated[SqlAlchemyFileRepository, Depends(get_file_repository)]
FileStorageDep = Annotated[FileStorage, Depends(get_storage)]
ImportRepoDep = Annotated[SqlAlchemyImportJobRepository, Depends(get_import_repository)]
UnitOfWorkDep = Annotated[SqlAlchemyUnitOfWork, Depends(get_unit_of_work)]
LoaderRepositoriesDep = Annotated[dict, Depends(get_loader_repositories)]
CompanyOverviewDep = Annotated[
    SqlAlchemyCompanyOverviewRepository, Depends(get_company_overview_repository)
]
SpreadsheetReaderDep = Annotated[SpreadsheetReader, Depends(get_spreadsheet_reader)]
InvoiceScanRepoDep = Annotated[
    SqlAlchemyInvoiceScanRepository, Depends(get_invoice_scan_repository)
]
InvoiceExtractorDep = Annotated[InvoiceExtractor, Depends(get_extractor)]
CreditRepoDep = Annotated[SqlAlchemyCreditRepository, Depends(get_credit_repository)]
CreditServiceDep = Annotated[CreditService, Depends(get_credit_service)]
