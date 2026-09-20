import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateRoleCommand(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class UpdateRoleCommand(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    # Sent, this replaces the grant set wholesale -- there is no partial merge,
    # so a role's permissions are always exactly what the last write said.
    permissions: list[str] | None = None


class RoleDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    code: str
    name: str
    description: str | None
    is_system: bool
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class PermissionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    module: str
    description: str
