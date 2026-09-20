import uuid

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notifications.entities.notification import Notification
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.platform import NotificationModel
from app.infrastructure.database.repositories.mappers import notification_to_domain


class SqlAlchemyNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, company_id: uuid.UUID, notification_id: uuid.UUID
    ) -> Notification | None:
        stmt = select(NotificationModel).where(
            NotificationModel.id == notification_id,
            NotificationModel.company_id == company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return notification_to_domain(model) if model else None

    async def list(
        self, company_id: uuid.UUID, *, page: Page, only_unread: bool = False
    ) -> PaginatedResult[Notification]:
        filters = [NotificationModel.company_id == company_id]
        if only_unread:
            filters.append(NotificationModel.is_read.is_(False))

        total = (
            await self._session.execute(
                select(func.count()).select_from(NotificationModel).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(NotificationModel)
            .where(*filters)
            .order_by(NotificationModel.created_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[notification_to_domain(row) for row in rows], total=total, page=page
        )

    async def add_if_absent(self, notification: Notification) -> Notification | None:
        """Insert unless an unread row already carries the same dedupe_key.

        The partial unique index does the deciding, so two workers running the
        low-stock sweep at once still produce one alert.
        """
        values = {
            "id": notification.id,
            "company_id": notification.company_id,
            "type": notification.type,
            "title": notification.title,
            "body": notification.body,
            "payload": notification.payload,
            "is_read": notification.is_read,
            "dedupe_key": notification.dedupe_key,
            "entity_id": notification.entity_id,
        }
        stmt = pg_insert(NotificationModel).values(**values)
        if notification.dedupe_key is not None:
            # The predicate has to match the partial index character for
            # character for PostgreSQL to infer it (`is_read = false`, not
            # `is_read IS false`), so it is spelled out rather than built from
            # the ORM comparison operators.
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["company_id", "dedupe_key"],
                index_where=text("dedupe_key IS NOT NULL AND is_read = false"),
            )
        result = await self._session.execute(stmt.returning(NotificationModel.id))
        inserted = result.scalar_one_or_none()
        if inserted is None:
            return None
        await self._session.flush()
        return await self.get_by_id(notification.company_id, inserted)

    async def mark_read(self, company_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
        stmt = select(NotificationModel).where(
            NotificationModel.id == notification_id,
            NotificationModel.company_id == company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Notification {notification_id} not found")
        model.is_read = True
        await self._session.flush()
        return notification_to_domain(model)

    async def count_unread(self, company_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(NotificationModel)
            .where(
                NotificationModel.company_id == company_id,
                NotificationModel.is_read.is_(False),
            )
        )
        return (await self._session.execute(stmt)).scalar_one()
