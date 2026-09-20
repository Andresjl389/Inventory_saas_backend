import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit.entities.audit_entry import AuditAction, AuditEntry
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.platform import AuditLogModel
from app.infrastructure.database.repositories.mappers import audit_entry_to_domain


class SqlAlchemyAuditRepository:
    """Append-only: there is no update or delete, and the RLS policies do not
    define one either."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditEntry) -> AuditEntry:
        model = AuditLogModel(
            id=entry.id,
            company_id=entry.company_id,
            actor_user_id=entry.actor_user_id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            payload=entry.payload,
            ip_address=entry.ip_address,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return audit_entry_to_domain(model)

    async def list(
        self,
        *,
        page: Page,
        company_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        action: AuditAction | None = None,
    ) -> PaginatedResult[AuditEntry]:
        filters = []
        if company_id is not None:
            filters.append(AuditLogModel.company_id == company_id)
        if actor_user_id is not None:
            filters.append(AuditLogModel.actor_user_id == actor_user_id)
        if action is not None:
            filters.append(AuditLogModel.action == action)

        total = (
            await self._session.execute(
                select(func.count()).select_from(AuditLogModel).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(AuditLogModel)
            .where(*filters)
            .order_by(AuditLogModel.created_at.desc(), AuditLogModel.id.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[audit_entry_to_domain(row) for row in rows], total=total, page=page
        )
