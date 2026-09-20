"""Authentication: turn a bearer token into a User, then publish that identity
to the database transaction so RLS policies can use it."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.identity.entities.user import User
from app.domain.identity.exceptions import InactiveUserError, InvalidCredentialsError
from app.infrastructure.database.tenant_context import set_current_user, set_platform_admin
from app.presentation.api.dependencies.database import SessionDep
from app.presentation.api.dependencies.repositories import UserRepoDep
from app.shared.logging.context import user_id_var
from app.shared.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    users: UserRepoDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise InvalidCredentialsError("Missing bearer token", code="UNAUTHORIZED")

    payload = decode_token(credentials.credentials, expected_type="access")

    user = await users.get_by_id(payload.user_id)
    if user is None:
        raise InvalidCredentialsError()
    if not user.is_active:
        raise InactiveUserError()

    # RLS on companies/company_members reads app.current_user_id().
    await set_current_user(session, user.id)
    if user.is_superuser:
        # The flag comes from the database row, never from the token: a stolen
        # token cannot promote itself, and demoting a user takes effect on
        # their next request.
        await set_platform_admin(session, True)
    user_id_var.set(str(user.id))
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
