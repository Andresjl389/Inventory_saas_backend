"""Translation between ORM models and domain entities.

Kept in one place so the domain never leaks SQLAlchemy types and repositories
stay short.
"""

from app.domain.identity.entities.user import User
from app.domain.products.entities.category import Category
from app.domain.products.entities.product import Product
from app.domain.tenants.entities.company import Company
from app.domain.tenants.entities.company_member import CompanyMember
from app.infrastructure.database.models.company import CompanyMemberModel, CompanyModel
from app.infrastructure.database.models.product import CategoryModel, ProductModel
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
