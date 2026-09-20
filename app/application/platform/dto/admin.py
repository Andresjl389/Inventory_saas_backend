import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.billing.entities.plan import SubscriptionStatus
from app.domain.shared.document import DocumentType
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.entities.company import CompanyStatus


class ProvisionCompanyCommand(BaseModel):
    """Create a company and give it an owner in one call.

    The owner is either an existing account (matched by email) or a new one; in
    the second case `owner_password` is required.
    """

    name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    owner_password: str | None = Field(default=None, min_length=8, max_length=72)
    owner_first_name: str | None = Field(default=None, max_length=100)
    owner_last_name: str | None = Field(default=None, max_length=100)
    legal_name: str | None = Field(default=None, max_length=200)
    document_type: DocumentType | None = None
    document_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    plan_code: str | None = Field(default=None, max_length=64)


class UpdateCompanyCommand(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    document_type: DocumentType | None = None
    document_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    status: CompanyStatus | None = None


class ListCompaniesQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    search: str | None = None
    status: CompanyStatus | None = None


class CreateUserCommand(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    is_superuser: bool = False


class UpdateUserCommand(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=72)
    is_active: bool | None = None
    is_superuser: bool | None = None


class ListUsersQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    search: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None


class AdminUserDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None
    created_at: datetime


class AdminUserPageDTO(BaseModel):
    items: list[AdminUserDTO]
    total: int
    page: int
    size: int
    pages: int


class AdminCompanyDTO(BaseModel):
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


class AdminCompanyPageDTO(BaseModel):
    items: list[AdminCompanyDTO]
    total: int
    page: int
    size: int
    pages: int


class ProvisionedCompanyDTO(BaseModel):
    company: AdminCompanyDTO
    owner: AdminUserDTO
    owner_created: bool
    subscription: "SubscriptionDTO | None" = None


class CreatePlanCommand(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    price_monthly: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    # 0 means unlimited.
    max_users: int = Field(default=0, ge=0)
    max_products: int = Field(default=0, ge=0)
    max_warehouses: int = Field(default=0, ge=0)


class UpdatePlanCommand(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    price_monthly: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    max_users: int | None = Field(default=None, ge=0)
    max_products: int | None = Field(default=None, ge=0)
    max_warehouses: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class AssignSubscriptionCommand(BaseModel):
    plan_code: str = Field(min_length=1, max_length=64)
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    period_days: int = Field(default=30, ge=1, le=3650)


class PlanDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    price_monthly: Decimal
    max_users: int
    max_products: int
    max_warehouses: int
    is_active: bool


class SubscriptionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    started_at: datetime | None
    current_period_end: datetime | None
    cancelled_at: datetime | None


class PlatformStatsDTO(BaseModel):
    companies_total: int
    companies_active: int
    companies_suspended: int
    users_total: int
    users_active: int
    platform_admins: int


ProvisionedCompanyDTO.model_rebuild()
