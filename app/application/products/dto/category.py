import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateCategoryCommand(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None


class UpdateCategoryCommand(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None


class CategoryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
