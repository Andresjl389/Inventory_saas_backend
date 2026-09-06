from app.application.identity.dto.auth import LoginCommand, TokenPairDTO
from app.domain.identity.exceptions import InactiveUserError, InvalidCredentialsError
from app.domain.identity.repositories.user_repository import UserRepository
from app.shared.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)

# Hashing a throwaway password on the "user not found" path keeps login timing
# roughly constant, so the endpoint cannot be used to enumerate accounts.
_DUMMY_HASH = hash_password("timing-equalizer")


class AuthenticateUserUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, command: LoginCommand) -> TokenPairDTO:
        user = await self._users.get_by_email(command.email)

        if user is None:
            verify_password(command.password, _DUMMY_HASH)
            raise InvalidCredentialsError()

        if not verify_password(command.password, user.password_hash):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        user.register_login()
        await self._users.update(user)

        return TokenPairDTO(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )
