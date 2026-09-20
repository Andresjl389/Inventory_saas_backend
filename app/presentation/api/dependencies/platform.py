"""Platform-administration guard.

Endpoints under /api/v1/admin are for operators of the SaaS itself. They are
gated on `users.is_superuser` -- a column in the database, never a claim in the
token -- and the same check is what raised `app.is_platform_admin` for this
transaction, so the API guard and the RLS policies can never disagree.
"""

from typing import Annotated

from fastapi import Depends

from app.domain.identity.entities.platform_admin import require_platform_admin
from app.domain.identity.entities.user import User
from app.presentation.api.dependencies.auth import CurrentUserDep


async def get_platform_admin(user: CurrentUserDep) -> User:
    return require_platform_admin(user)


PlatformAdminDep = Annotated[User, Depends(get_platform_admin)]
