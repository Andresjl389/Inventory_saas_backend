"""Per-company counters for the supervision console.

Runs inside one company's tenant scope -- the caller enters it first -- so the
same RLS that protects a member's request protects this one.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.sales.entities.sale import SaleStatus
from app.infrastructure.database.models.company import CompanyMemberModel
from app.infrastructure.database.models.inventory import ProductStockModel, WarehouseModel
from app.infrastructure.database.models.partner import CustomerModel, SupplierModel
from app.infrastructure.database.models.product import ProductModel
from app.infrastructure.database.models.purchase import PurchaseModel
from app.infrastructure.database.models.sale import SaleModel

ZERO = Decimal("0")


class SqlAlchemyCompanyOverviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def counters(self, company_id: uuid.UUID, *, since: datetime | None) -> dict:
        members, active_members = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count().filter(CompanyMemberModel.is_active.is_(True)),
                )
                .select_from(CompanyMemberModel)
                .where(CompanyMemberModel.company_id == company_id)
            )
        ).one()

        products, active_products = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count().filter(ProductModel.is_active.is_(True)),
                )
                .select_from(ProductModel)
                .where(ProductModel.company_id == company_id)
            )
        ).one()

        warehouses = (
            await self._session.execute(
                select(func.count())
                .select_from(WarehouseModel)
                .where(WarehouseModel.company_id == company_id)
            )
        ).scalar_one()

        customers = (
            await self._session.execute(
                select(func.count())
                .select_from(CustomerModel)
                .where(CustomerModel.company_id == company_id)
            )
        ).scalar_one()

        suppliers = (
            await self._session.execute(
                select(func.count())
                .select_from(SupplierModel)
                .where(SupplierModel.company_id == company_id)
            )
        ).scalar_one()

        sale_filters = [
            SaleModel.company_id == company_id,
            SaleModel.status == SaleStatus.COMPLETED,
        ]
        if since is not None:
            sale_filters.append(SaleModel.created_at >= since)

        sales_count, revenue, last_sale_at = (
            await self._session.execute(
                select(
                    func.count(SaleModel.id),
                    func.coalesce(func.sum(SaleModel.total), 0),
                    func.max(SaleModel.created_at),
                ).where(*sale_filters)
            )
        ).one()

        purchases_count = (
            await self._session.execute(
                select(func.count())
                .select_from(PurchaseModel)
                .where(PurchaseModel.company_id == company_id)
            )
        ).scalar_one()

        # NUMERIC(18,4) * NUMERIC(18,4) widens to 8 decimals; bring it back.
        units, stock_value = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(ProductStockModel.quantity), 0),
                    func.round(
                        func.coalesce(
                            func.sum(ProductStockModel.quantity * ProductModel.cost_price), 0
                        ),
                        4,
                    ),
                )
                .select_from(ProductStockModel)
                .join(ProductModel, ProductModel.id == ProductStockModel.product_id)
                .where(ProductStockModel.company_id == company_id)
            )
        ).one()

        return {
            "members": members,
            "active_members": active_members,
            "products": products,
            "active_products": active_products,
            "warehouses": warehouses,
            "customers": customers,
            "suppliers": suppliers,
            "sales_count": sales_count,
            "sales_revenue": revenue,
            "purchases_count": purchases_count,
            "stock_units": units,
            "stock_value": stock_value,
            "last_sale_at": last_sale_at,
        }
