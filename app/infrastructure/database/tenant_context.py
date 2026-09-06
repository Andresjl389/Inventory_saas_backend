"""Bridge between the application's TenantContext and PostgreSQL RLS.

`set_config(..., is_local => true)` is the parameterised equivalent of
`SET LOCAL`: the value is scoped to the current transaction and, unlike a
literal `SET LOCAL`, it accepts a bind parameter so the company id can never be
concatenated into SQL.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.rls import TENANT_SETTING, USER_SETTING

_SET_CONFIG = text("SELECT set_config(:key, :value, true)")


async def set_current_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(_SET_CONFIG, {"key": USER_SETTING, "value": str(user_id)})


async def set_current_company(session: AsyncSession, company_id: uuid.UUID) -> None:
    await session.execute(_SET_CONFIG, {"key": TENANT_SETTING, "value": str(company_id)})


async def clear_tenant_context(session: AsyncSession) -> None:
    for key in (USER_SETTING, TENANT_SETTING):
        await session.execute(_SET_CONFIG, {"key": key, "value": ""})
