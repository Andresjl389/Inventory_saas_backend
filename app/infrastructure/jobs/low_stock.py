"""Low-stock sweep.

Runs company by company under that company's own tenant context, so the job is
subject to exactly the same RLS as a request would be. The only cross-tenant
step is listing which companies to visit.
"""

import logging
import uuid

from sqlalchemy import select

from app.domain.notifications.entities.notification import Notification, NotificationType
from app.domain.tenants.entities.company import CompanyStatus
from app.infrastructure.database.models.company import CompanyModel
from app.infrastructure.database.repositories.notification_repository import (
    SqlAlchemyNotificationRepository,
)
from app.infrastructure.database.repositories.report_repository import SqlAlchemyReportRepository
from app.infrastructure.jobs.context import platform_session, tenant_session

logger = logging.getLogger("app.jobs.low_stock")

MAX_ALERTS_PER_COMPANY = 100


async def active_company_ids() -> list[uuid.UUID]:
    async with platform_session() as session:
        stmt = select(CompanyModel.id).where(CompanyModel.status == CompanyStatus.ACTIVE)
        return list((await session.execute(stmt)).scalars().all())


async def sweep_company(company_id: uuid.UUID) -> int:
    created = 0
    async with tenant_session(company_id) as session:
        rows = await SqlAlchemyReportRepository(session).low_stock(
            company_id, limit=MAX_ALERTS_PER_COMPANY
        )
        notifications = SqlAlchemyNotificationRepository(session)

        for row in rows:
            # One alert per product+warehouse while it stays unread; the
            # partial unique index enforces it, so a second sweep is a no-op.
            key = f"low_stock:{row.product_id}:{row.warehouse_id or 'none'}"
            where = f" in {row.warehouse_name}" if row.warehouse_name else ""
            inserted = await notifications.add_if_absent(
                Notification(
                    company_id=company_id,
                    type=NotificationType.LOW_STOCK,
                    title=f"Low stock: {row.product_name}",
                    body=(
                        f"{row.product_name} ({row.sku}){where} is down to {row.quantity}, "
                        f"at or below its threshold of {row.min_stock}."
                    ),
                    payload={
                        "product_id": str(row.product_id),
                        "sku": row.sku,
                        "warehouse_id": str(row.warehouse_id) if row.warehouse_id else None,
                        "quantity": str(row.quantity),
                        "min_stock": str(row.min_stock),
                    },
                    dedupe_key=key,
                    entity_id=row.product_id,
                )
            )
            if inserted is not None:
                created += 1

    return created


async def sweep_low_stock(ctx: dict | None = None) -> dict[str, int]:
    """Arq entry point. Returns a small summary for the job log."""
    companies = await active_company_ids()
    alerts = 0
    for company_id in companies:
        try:
            alerts += await sweep_company(company_id)
        except Exception:
            # One tenant's bad data must not stop the sweep for everybody else.
            logger.exception("low stock sweep failed", extra={"company_id": str(company_id)})

    logger.info(
        "low stock sweep finished",
        extra={"companies": len(companies), "alerts_created": alerts},
    )
    return {"companies": len(companies), "alerts_created": alerts}
