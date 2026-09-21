from app.application.identity.dto.auth import RegisterUserCommand, UserDTO
from app.domain.identity.entities.user import User
from app.domain.identity.exceptions import EmailAlreadyRegisteredError
from app.domain.identity.repositories.user_repository import UserRepository
from app.domain.identity.value_objects.email import Email
from app.shared.security import hash_password


class RegisterUserUseCase:
    """Create an account, and only an account.

    The new user belongs to no company. Membership is granted by a company's
    own administrator (`POST /companies/current/members`) or by a platform
    administrator (`POST /admin/companies/{id}/members`) -- always against a
    company that already exists, identified by its id.
    """

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, command: RegisterUserCommand) -> UserDTO:
        email = Email(command.email).value

        if await self._users.exists_by_email(email):
            raise EmailAlreadyRegisteredError()

        user = await self._users.add(
            User(
                email=email,
                password_hash=hash_password(command.password),
                first_name=command.first_name.strip(),
                last_name=command.last_name.strip(),
            )
        )
        return UserDTO.model_validate(user, from_attributes=True)
