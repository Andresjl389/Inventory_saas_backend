import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateWarehouseCommand(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    address: str | None = None


class UpdateWarehouseCommand(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    address: str | None = None
    is_active: bool | None = None


class WarehouseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
