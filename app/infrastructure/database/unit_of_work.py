from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def savepoint(self, *, commit: bool) -> AsyncIterator[None]:
        nested = await self._session.begin_nested()
        try:
            yield
        except Exception:
            await nested.rollback()
            raise

        if commit:
            await nested.commit()
        else:
            # A dry run: everything the loader did is undone, including any
            # constraint the database accepted along the way.
            await nested.rollback()
