from app.application.identity.dto.auth import RefreshCommand, TokenPairDTO
from app.domain.identity.exceptions import InactiveUserError, InvalidCredentialsError
from app.domain.identity.repositories.user_repository import UserRepository
from app.shared.security import create_access_token, create_refresh_token, decode_token


class RefreshTokensUseCase:
    """Rotate a refresh token for a fresh pair.

    A denylist of revoked JTIs (Redis) is the natural next step; the token's
    `jti` is already issued for that purpose.
    """

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, command: RefreshCommand) -> TokenPairDTO:
        payload = decode_token(command.refresh_token, expected_type="refresh")

        user = await self._users.get_by_id(payload.user_id)
        if user is None:
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InactiveUserError()

        return TokenPairDTO(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )
