import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.reports.repositories.report_repository import (
    LowStockRow,
    ProductSales,
    SalesSummary,
    WarehouseValuation,
)
from app.domain.sales.entities.sale import SaleStatus
from app.infrastructure.database.models.inventory import ProductStockModel, WarehouseModel
from app.infrastructure.database.models.product import ProductModel
from app.infrastructure.database.models.sale import SaleItemModel, SaleModel

ZERO = Decimal("0")


class SqlAlchemyReportRepository:
    """Every query filters by company_id explicitly and runs under the tenant's
    RLS context, so a report can never aggregate across tenants."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _sale_filters(
        self, company_id: uuid.UUID, since: datetime | None, until: datetime | None
    ) -> list:
        # Only COMPLETED sales count: drafts have not happened and cancelled or
        # refunded ones gave the money back.
        filters = [
            SaleModel.company_id == company_id,
            SaleModel.status == SaleStatus.COMPLETED,
        ]
        if since is not None:
            filters.append(SaleModel.created_at >= since)
        if until is not None:
            filters.append(SaleModel.created_at <= until)
        return filters

    async def sales_summary(
        self, company_id: uuid.UUID, *, since: datetime | None, until: datetime | None
    ) -> SalesSummary:
        filters = self._sale_filters(company_id, since, until)
        row = (
            await self._session.execute(
                select(
                    func.count(SaleModel.id),
                    func.coalesce(func.sum(SaleModel.total), 0),
                    func.coalesce(func.sum(SaleModel.discount), 0),
                    func.coalesce(func.sum(SaleModel.tax), 0),
                ).where(*filters)
            )
        ).one()

        count, revenue, discount, tax = row
        average = (revenue / count) if count else ZERO
        return SalesSummary(
            sales_count=count,
            revenue=revenue,
            discount=discount,
            tax=tax,
            average_ticket=Decimal(average).quantize(Decimal("0.0001")),
        )

    async def top_products(
        self,
        company_id: uuid.UUID,
        *,
        since: datetime | None,
        until: datetime | None,
        limit: int,
    ) -> list[ProductSales]:
        filters = self._sale_filters(company_id, since, until)
        stmt = (
            select(
                ProductModel.id,
                ProductModel.name,
                ProductModel.sku,
                func.sum(SaleItemModel.quantity),
                func.sum(SaleItemModel.total),
            )
            .join(SaleModel, SaleModel.id == SaleItemModel.sale_id)
            .join(ProductModel, ProductModel.id == SaleItemModel.product_id)
            .where(*filters)
            .group_by(ProductModel.id, ProductModel.name, ProductModel.sku)
            .order_by(func.sum(SaleItemModel.total).desc())
            .limit(limit)
        )
        return [
            ProductSales(
                product_id=row[0],
                product_name=row[1],
                sku=row[2],
                quantity=row[3],
                revenue=row[4],
            )
            for row in (await self._session.execute(stmt)).all()
        ]

    async def inventory_valuation(self, company_id: uuid.UUID) -> list[WarehouseValuation]:
        stmt = (
            select(
                WarehouseModel.id,
                WarehouseModel.name,
                func.coalesce(func.sum(ProductStockModel.quantity), 0),
                # NUMERIC(18,4) * NUMERIC(18,4) widens to 8 decimals; round it
                # back to the money scale so the API never emits 56.00000000.
                func.round(
                    func.coalesce(
                        func.sum(ProductStockModel.quantity * ProductModel.cost_price), 0
                    ),
                    4,
                ),
                func.round(
                    func.coalesce(
                        func.sum(ProductStockModel.quantity * ProductModel.sale_price), 0
                    ),
                    4,
                ),
            )
            .select_from(WarehouseModel)
            .outerjoin(
                ProductStockModel,
                (ProductStockModel.warehouse_id == WarehouseModel.id)
                & (ProductStockModel.company_id == company_id),
            )
            .outerjoin(ProductModel, ProductModel.id == ProductStockModel.product_id)
            .where(WarehouseModel.company_id == company_id)
            .group_by(WarehouseModel.id, WarehouseModel.name)
            .order_by(WarehouseModel.name)
        )
        return [
            WarehouseValuation(
                warehouse_id=row[0],
                warehouse_name=row[1],
                units=row[2],
                cost_value=row[3],
                retail_value=row[4],
            )
            for row in (await self._session.execute(stmt)).all()
        ]

    async def low_stock(self, company_id: uuid.UUID, *, limit: int) -> list[LowStockRow]:
        """Products at or below their reorder threshold, per warehouse.

        A product with a threshold and no stock row at all still counts: "we
        have none of it" is exactly what the report is for, so the join is an
        outer one and a missing row reads as zero.
        """
        quantity = func.coalesce(ProductStockModel.quantity, 0)
        stmt = (
            select(
                ProductModel.id,
                ProductModel.name,
                ProductModel.sku,
                ProductStockModel.warehouse_id,
                WarehouseModel.name,
                quantity,
                ProductModel.min_stock,
            )
            .select_from(ProductModel)
            .outerjoin(
                ProductStockModel,
                (ProductStockModel.product_id == ProductModel.id)
                & (ProductStockModel.company_id == company_id),
            )
            .outerjoin(WarehouseModel, WarehouseModel.id == ProductStockModel.warehouse_id)
            .where(
                ProductModel.company_id == company_id,
                ProductModel.is_active.is_(True),
                ProductModel.min_stock > 0,
                quantity <= ProductModel.min_stock,
            )
            .order_by(
                case((ProductModel.min_stock == 0, 0), else_=quantity / ProductModel.min_stock),
                ProductModel.name,
            )
            .limit(limit)
        )
        return [
            LowStockRow(
                product_id=row[0],
                product_name=row[1],
                sku=row[2],
                warehouse_id=row[3],
                warehouse_name=row[4],
                quantity=row[5],
                min_stock=row[6],
            )
            for row in (await self._session.execute(stmt)).all()
        ]
