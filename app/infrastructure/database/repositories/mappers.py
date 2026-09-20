"""Translation between ORM models and domain entities.

Kept in one place so the domain never leaks SQLAlchemy types and repositories
stay short.
"""

from app.domain.audit.entities.audit_entry import AuditEntry
from app.domain.authorization.entities.role import Permission, Role
from app.domain.billing.entities.plan import Plan, Subscription
from app.domain.customers.entities.customer import Customer
from app.domain.files.entities.stored_file import StoredFile
from app.domain.identity.entities.user import User
from app.domain.imports.entities.import_job import ImportJob, ImportRowError
from app.domain.inventory.entities.product_stock import ProductStock
from app.domain.inventory.entities.stock_movement import StockMovement
from app.domain.inventory.entities.warehouse import Warehouse
from app.domain.notifications.entities.notification import Notification
from app.domain.products.entities.category import Category
from app.domain.products.entities.product import Product
from app.domain.purchases.entities.purchase import Purchase, PurchaseItem
from app.domain.sales.entities.sale import Sale, SaleItem
from app.domain.suppliers.entities.supplier import Supplier
from app.domain.tenants.entities.company import Company
from app.domain.tenants.entities.company_member import CompanyMember
from app.infrastructure.database.models.authorization import PermissionModel, RoleModel
from app.infrastructure.database.models.company import CompanyMemberModel, CompanyModel
from app.infrastructure.database.models.file import FileModel
from app.infrastructure.database.models.imports import ImportErrorModel, ImportJobModel
from app.infrastructure.database.models.inventory import (
    ProductStockModel,
    StockMovementModel,
    WarehouseModel,
)
from app.infrastructure.database.models.partner import CustomerModel, SupplierModel
from app.infrastructure.database.models.platform import (
    AuditLogModel,
    NotificationModel,
    PlanModel,
    SubscriptionModel,
)
from app.infrastructure.database.models.product import CategoryModel, ProductModel
from app.infrastructure.database.models.purchase import PurchaseModel
from app.infrastructure.database.models.sale import SaleModel
from app.infrastructure.database.models.user import UserModel


def user_to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        email=model.email,
        password_hash=model.password_hash,
        first_name=model.first_name,
        last_name=model.last_name,
        is_active=model.is_active,
        is_superuser=model.is_superuser,
        last_login_at=model.last_login_at,
    )


def company_to_domain(model: CompanyModel) -> Company:
    return Company(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        name=model.name,
        legal_name=model.legal_name,
        document_type=model.document_type,
        document_number=model.document_number,
        email=model.email,
        phone=model.phone,
        status=model.status,
    )


def member_to_domain(model: CompanyMemberModel, role_code: str = "") -> CompanyMember:
    """`role_code` comes from a join; it is display data, not authority."""
    return CompanyMember(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        user_id=model.user_id,
        role_id=model.role_id,
        role_code=role_code,
        is_active=model.is_active,
    )


def category_to_domain(model: CategoryModel) -> Category:
    return Category(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        name=model.name,
        description=model.description,
    )


def product_to_domain(model: ProductModel) -> Product:
    return Product(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        category_id=model.category_id,
        name=model.name,
        description=model.description,
        sku=model.sku,
        barcode=model.barcode,
        cost_price=model.cost_price,
        sale_price=model.sale_price,
        is_active=model.is_active,
        min_stock=model.min_stock,
    )


def warehouse_to_domain(model: WarehouseModel) -> Warehouse:
    return Warehouse(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        name=model.name,
        address=model.address,
        is_active=model.is_active,
    )


def product_stock_to_domain(model: ProductStockModel) -> ProductStock:
    return ProductStock(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        product_id=model.product_id,
        warehouse_id=model.warehouse_id,
        quantity=model.quantity,
    )


def stock_movement_to_domain(model: StockMovementModel) -> StockMovement:
    return StockMovement(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.created_at,
        company_id=model.company_id,
        product_id=model.product_id,
        warehouse_id=model.warehouse_id,
        movement_type=model.movement_type,
        quantity=model.quantity,
        reference_type=model.reference_type,
        reference_id=model.reference_id,
        notes=model.notes,
        created_by=model.created_by,
    )


def customer_to_domain(model: CustomerModel) -> Customer:
    return Customer(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        name=model.name,
        document_type=model.document_type,
        document_number=model.document_number,
        email=model.email,
        phone=model.phone,
        address=model.address,
        is_active=model.is_active,
    )


def supplier_to_domain(model: SupplierModel) -> Supplier:
    return Supplier(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        name=model.name,
        document_type=model.document_type,
        document_number=model.document_number,
        email=model.email,
        phone=model.phone,
        address=model.address,
        is_active=model.is_active,
    )


def sale_to_domain(model: SaleModel) -> Sale:
    sale = Sale(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        customer_id=model.customer_id,
        warehouse_id=model.warehouse_id,
        status=model.status,
        notes=model.notes,
        created_by=model.created_by,
        items=[
            SaleItem(
                id=item.id,
                created_at=item.created_at,
                updated_at=item.updated_at,
                company_id=item.company_id,
                sale_id=item.sale_id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount=item.discount,
                tax=item.tax,
            )
            for item in model.items
        ],
    )
    # Totals are recomputed from the items by Sale.__post_init__; the stored
    # header is the cache, the items are the truth.
    return sale


def purchase_to_domain(model: PurchaseModel) -> Purchase:
    return Purchase(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        supplier_id=model.supplier_id,
        warehouse_id=model.warehouse_id,
        status=model.status,
        notes=model.notes,
        created_by=model.created_by,
        items=[
            PurchaseItem(
                id=item.id,
                created_at=item.created_at,
                updated_at=item.updated_at,
                company_id=item.company_id,
                purchase_id=item.purchase_id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_cost=item.unit_cost,
                discount=item.discount,
                tax=item.tax,
            )
            for item in model.items
        ],
    )


def role_to_domain(model: RoleModel, permissions: frozenset[str] = frozenset()) -> Role:
    return Role(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        code=model.code,
        name=model.name,
        description=model.description,
        is_system=model.is_system,
        permissions=permissions,
    )


def permission_to_domain(model: PermissionModel) -> Permission:
    return Permission(
        id=model.id,
        code=model.code,
        module=model.module,
        description=model.description,
    )


def audit_entry_to_domain(model: AuditLogModel) -> AuditEntry:
    return AuditEntry(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.created_at,
        action=model.action,
        company_id=model.company_id,
        actor_user_id=model.actor_user_id,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        payload=model.payload or {},
        ip_address=model.ip_address,
    )


def plan_to_domain(model: PlanModel) -> Plan:
    return Plan(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        code=model.code,
        name=model.name,
        description=model.description,
        price_monthly=model.price_monthly,
        max_users=model.max_users,
        max_products=model.max_products,
        max_warehouses=model.max_warehouses,
        is_active=model.is_active,
    )


def subscription_to_domain(model: SubscriptionModel) -> Subscription:
    return Subscription(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        plan_id=model.plan_id,
        status=model.status,
        started_at=model.started_at,
        current_period_end=model.current_period_end,
        cancelled_at=model.cancelled_at,
    )


def notification_to_domain(model: NotificationModel) -> Notification:
    return Notification(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        type=model.type,
        title=model.title,
        body=model.body,
        payload=model.payload or {},
        is_read=model.is_read,
        dedupe_key=model.dedupe_key,
        entity_id=model.entity_id,
    )


def stored_file_to_domain(model: FileModel) -> StoredFile:
    return StoredFile(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        owner_type=model.owner_type,
        owner_id=model.owner_id,
        filename=model.filename,
        content_type=model.content_type,
        size_bytes=model.size_bytes,
        storage_key=model.storage_key,
        checksum=model.checksum,
        uploaded_by=model.uploaded_by,
    )


def import_job_to_domain(model: ImportJobModel) -> ImportJob:
    return ImportJob(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        entity=model.entity,
        file_id=model.file_id,
        filename=model.filename,
        status=model.status,
        mapping=dict(model.mapping or {}),
        options=dict(model.options or {}),
        detected_columns=list(model.detected_columns or []),
        stats=dict(model.stats or {}),
        failure_reason=model.failure_reason,
        created_by=model.created_by,
    )


def import_error_to_domain(model: ImportErrorModel) -> ImportRowError:
    return ImportRowError(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        job_id=model.job_id,
        row_number=model.row_number,
        column=model.column,
        field_key=model.field_key,
        value=model.value,
        message=model.message,
    )
