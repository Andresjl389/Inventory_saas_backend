"""Application-level DTOs.

Pydantic is used for validation only; these objects carry no persistence or
HTTP concerns and can be reused by a CLI or a worker.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.shared.config.settings import settings


class RegisterUserCommand(BaseModel):
    """Signing up creates an *account*, nothing else.

    Companies are created by a platform administrator, who names the owner at
    the same time. Letting a sign-up form conjure a company from a typed name
    meant every typo became a new tenant and nobody could tell which of them
    was real.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


class LoginCommand(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshCommand(BaseModel):
    refresh_token: str


class UserDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    is_active: bool
    created_at: datetime


class TokenPairDTO(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(default_factory=lambda: settings.access_token_expire_minutes * 60)
