"""Composition root for repositories.

Use cases depend on the domain Protocols; the concrete SQLAlchemy classes are
only ever named here.
"""

from typing import Annotated

from fastapi import Depends

from app.application.inventory.services.stock_service import StockService
from app.infrastructure.database.repositories.category_repository import (
    SqlAlchemyCategoryRepository,
)
from app.infrastructure.database.repositories.company_member_repository import (
    SqlAlchemyCompanyMemberRepository,
)
from app.infrastructure.database.repositories.company_repository import SqlAlchemyCompanyRepository
from app.infrastructure.database.repositories.partner_repository import (
    SqlAlchemyCustomerRepository,
    SqlAlchemySupplierRepository,
)
from app.infrastructure.database.repositories.product_repository import SqlAlchemyProductRepository
from app.infrastructure.database.repositories.purchase_repository import (
    SqlAlchemyPurchaseRepository,
)
from app.infrastructure.database.repositories.sale_repository import SqlAlchemySaleRepository
from app.infrastructure.database.repositories.stock_repository import (
    SqlAlchemyStockMovementRepository,
    SqlAlchemyStockRepository,
)
from app.infrastructure.database.repositories.tenant_scope import SqlAlchemyTenantScope
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from app.infrastructure.database.repositories.warehouse_repository import (
    SqlAlchemyWarehouseRepository,
)
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


def get_tenant_scope(session: SessionDep) -> SqlAlchemyTenantScope:
    return SqlAlchemyTenantScope(session)


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
TenantScopeDep = Annotated[SqlAlchemyTenantScope, Depends(get_tenant_scope)]
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
