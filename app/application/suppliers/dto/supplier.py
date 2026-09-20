import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.shared.document import DocumentType
from app.domain.shared.pagination import MAX_PAGE_SIZE


class CreateSupplierCommand(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    document_type: DocumentType | None = None
    document_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None


class UpdateSupplierCommand(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    document_type: DocumentType | None = None
    document_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    is_active: bool | None = None


class ListSuppliersQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    search: str | None = None
    is_active: bool | None = None


class SupplierDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    document_type: DocumentType | None
    document_number: str | None
    email: str | None
    phone: str | None
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SupplierPageDTO(BaseModel):
    items: list[SupplierDTO]
    total: int
    page: int
    size: int
    pages: int
