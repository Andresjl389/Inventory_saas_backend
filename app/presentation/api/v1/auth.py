import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel

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
from app.presentation.api.dependencies.repositories import (
    CompanyRepoDep,
    MemberRepoDep,
    TenantScopeDep,
    UserRepoDep,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterResponse(BaseModel):
    user: UserDTO
    company_id: uuid.UUID | None = None


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    command: RegisterUserCommand,
    users: UserRepoDep,
    companies: CompanyRepoDep,
    members: MemberRepoDep,
    tenant_scope: TenantScopeDep,
) -> RegisterResponse:
    use_case = RegisterUserUseCase(users, companies, members, tenant_scope)
    user, company_id = await use_case.execute(command)
    return RegisterResponse(user=user, company_id=company_id)


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
