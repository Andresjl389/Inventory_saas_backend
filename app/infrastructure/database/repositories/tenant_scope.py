import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.tenant_context import set_current_company


class SqlAlchemyTenantScope:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enter(self, company_id: uuid.UUID) -> None:
        await set_current_company(self._session, company_id)
