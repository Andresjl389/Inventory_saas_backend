"""Translation between ORM models and domain entities.

Kept in one place so the domain never leaks SQLAlchemy types and repositories
stay short.
"""

from app.domain.customers.entities.customer import Customer
from app.domain.identity.entities.user import User
from app.domain.inventory.entities.product_stock import ProductStock
from app.domain.inventory.entities.stock_movement import StockMovement
from app.domain.inventory.entities.warehouse import Warehouse
from app.domain.products.entities.category import Category
from app.domain.products.entities.product import Product
from app.domain.purchases.entities.purchase import Purchase, PurchaseItem
from app.domain.sales.entities.sale import Sale, SaleItem
from app.domain.suppliers.entities.supplier import Supplier
from app.domain.tenants.entities.company import Company
from app.domain.tenants.entities.company_member import CompanyMember
from app.infrastructure.database.models.company import CompanyMemberModel, CompanyModel
from app.infrastructure.database.models.inventory import (
    ProductStockModel,
    StockMovementModel,
    WarehouseModel,
)
from app.infrastructure.database.models.partner import CustomerModel, SupplierModel
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


def member_to_domain(model: CompanyMemberModel) -> CompanyMember:
    return CompanyMember(
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        company_id=model.company_id,
        user_id=model.user_id,
        role=model.role,
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
