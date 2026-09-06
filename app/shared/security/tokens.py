"""JWT access and refresh tokens.

The token identifies the *user* only. The active company is never trusted from
the token payload alone -- membership is revalidated on every request (see
`app.presentation.api.dependencies.tenant`).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from app.shared.config.settings import settings
from app.shared.exceptions import UnauthorizedError

TokenType = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class TokenPayload:
    user_id: uuid.UUID
    token_type: TokenType
    jti: uuid.UUID
    expires_at: datetime


def _create_token(user_id: uuid.UUID, token_type: TokenType, expires_in: timedelta) -> str:
    now = datetime.now(UTC)
    expires_at = now + expires_in
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: uuid.UUID) -> str:
    return _create_token(user_id, "access", timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(user_id: uuid.UUID) -> str:
    return _create_token(user_id, "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, *, expected_type: TokenType) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired", code="TOKEN_EXPIRED") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid token", code="INVALID_TOKEN") from exc

    if raw.get("type") != expected_type:
        raise UnauthorizedError(f"Expected a {expected_type} token", code="INVALID_TOKEN")

    try:
        return TokenPayload(
            user_id=uuid.UUID(raw["sub"]),
            token_type=expected_type,
            jti=uuid.UUID(raw["jti"]),
            expires_at=datetime.fromtimestamp(raw["exp"], tz=UTC),
        )
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Malformed token payload", code="INVALID_TOKEN") from exc
