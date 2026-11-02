"""Importing this package registers every model on `Base.metadata`.

Alembic's env.py relies on it for autogenerate.
"""

from app.infrastructure.database.models.authorization import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
)
from app.infrastructure.database.models.company import CompanyMemberModel, CompanyModel
from app.infrastructure.database.models.credit import (
    AccountEntryModel,
    CustomerBalanceModel,
)
from app.infrastructure.database.models.file import FileModel
from app.infrastructure.database.models.imports import ImportErrorModel, ImportJobModel
from app.infrastructure.database.models.inventory import (
    ProductStockModel,
    StockMovementModel,
    WarehouseModel,
)
from app.infrastructure.database.models.invoice import (
    InvoiceScanLineModel,
    InvoiceScanModel,
)
from app.infrastructure.database.models.partner import CustomerModel, SupplierModel
from app.infrastructure.database.models.platform import (
    AuditLogModel,
    NotificationModel,
    PlanModel,
    SubscriptionModel,
)
from app.infrastructure.database.models.product import CategoryModel, ProductModel
from app.infrastructure.database.models.purchase import PurchaseItemModel, PurchaseModel
from app.infrastructure.database.models.sale import SaleItemModel, SaleModel
from app.infrastructure.database.models.user import UserModel

__all__ = [
    "AccountEntryModel",
    "AuditLogModel",
    "CategoryModel",
    "CompanyMemberModel",
    "CompanyModel",
    "CustomerBalanceModel",
    "CustomerModel",
    "FileModel",
    "ImportErrorModel",
    "ImportJobModel",
    "InvoiceScanLineModel",
    "InvoiceScanModel",
    "NotificationModel",
    "PermissionModel",
    "PlanModel",
    "ProductModel",
    "ProductStockModel",
    "PurchaseItemModel",
    "PurchaseModel",
    "RoleModel",
    "RolePermissionModel",
    "SaleItemModel",
    "SaleModel",
    "StockMovementModel",
    "SubscriptionModel",
    "SupplierModel",
    "UserModel",
    "WarehouseModel",
]
