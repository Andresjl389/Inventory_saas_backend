import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.tenants.entities.company import CompanyStatus, DocumentType


class CreateCompanyCommand(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    document_type: DocumentType | None = None
    document_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)


class AddMemberCommand(BaseModel):
    email: EmailStr
    # A role *code*: one of the system roles (OWNER, ADMIN, SELLER,
    # INVENTORY_MANAGER) or a custom one this company defined.
    role: str = Field(min_length=1, max_length=64)


class ChangeMemberRoleCommand(BaseModel):
    role: str = Field(min_length=1, max_length=64)
    is_active: bool | None = None


class CompanyDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    legal_name: str | None
    document_type: DocumentType | None
    document_number: str | None
    email: str | None
    phone: str | None
    status: CompanyStatus
    created_at: datetime


class MembershipDTO(BaseModel):
    company_id: uuid.UUID
    company_name: str
    role: str
    is_active: bool


class CompanyMemberDTO(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    role_id: uuid.UUID
    is_active: bool
