import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.tenants.entities.company import CompanyStatus, DocumentType


class AddMemberCommand(BaseModel):
    """Attach a person to this company.

    If the email already has an account, that account is attached. If it does
    not, and a password is supplied, the account is created and attached in one
    step -- which is what lets a company administrator onboard their own team
    without a platform operator in the loop.
    """

    email: EmailStr
    # A role *code*: one of the system roles (OWNER, ADMIN, SELLER,
    # INVENTORY_MANAGER) or a custom one this company defined.
    role: str = Field(min_length=1, max_length=64)
    # Only used when the email has no account yet.
    password: str | None = Field(default=None, min_length=8, max_length=72)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)


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
