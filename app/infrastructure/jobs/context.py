"""Database sessions for background jobs.

A worker has no HTTP request and no authenticated user, so it cannot get a
tenant context the normal way. It gets one of two things instead:

* `platform_session()` -- the platform flag raised, used only to enumerate
  companies. It must never run business queries.
* `tenant_session(company_id)` -- scoped to exactly one company, identical to
  what a request from that tenant would see.

Splitting them keeps the cross-tenant surface of the worker to a single query.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import SessionFactory
from app.infrastructure.database.tenant_context import set_current_company, set_platform_admin


@asynccontextmanager
async def platform_session() -> AsyncIterator[AsyncSession]:
    session = SessionFactory()
    try:
        await set_platform_admin(session, True)
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def tenant_session(company_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    session = SessionFactory()
    try:
        await set_current_company(session, company_id)
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
