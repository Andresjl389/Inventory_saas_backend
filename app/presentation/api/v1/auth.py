from fastapi import APIRouter, status

from app.application.identity.dto.auth import (
    LoginCommand,
    RefreshCommand,
    RegisterUserCommand,
    TokenPairDTO,
    UserDTO,
)
from app.application.identity.use_cases.authenticate_user import AuthenticateUserUseCase
from app.application.identity.use_cases.refresh_tokens import RefreshTokensUseCase
from app.application.identity.use_cases.register_user import RegisterUserUseCase
from app.presentation.api.dependencies.auth import CurrentUserDep
from app.presentation.api.dependencies.repositories import UserRepoDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserDTO, status_code=status.HTTP_201_CREATED)
async def register(command: RegisterUserCommand, users: UserRepoDep) -> UserDTO:
    """Create an account. It belongs to no company yet.

    Companies are created by a platform administrator, who names the owner at
    the same time. To join an existing one, that company's administrator adds
    you from their team screen.
    """
    return await RegisterUserUseCase(users).execute(command)


@router.post("/login", response_model=TokenPairDTO)
async def login(command: LoginCommand, users: UserRepoDep) -> TokenPairDTO:
    return await AuthenticateUserUseCase(users).execute(command)


@router.post("/refresh", response_model=TokenPairDTO)
async def refresh(command: RefreshCommand, users: UserRepoDep) -> TokenPairDTO:
    return await RefreshTokensUseCase(users).execute(command)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(_: CurrentUserDep) -> None:
    """Stateless for now: the client drops its tokens.

    Server-side revocation needs a Redis denylist keyed by the token `jti`,
    which `decode_token` already returns.
    """
    return None


@router.get("/me", response_model=UserDTO)
async def me(user: CurrentUserDep) -> UserDTO:
    return UserDTO.model_validate(user, from_attributes=True)
