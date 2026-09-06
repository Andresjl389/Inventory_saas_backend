"""Company = tenant."""

from dataclasses import dataclass
from enum import StrEnum

from app.domain.shared.entities import BaseEntity


class CompanyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    INACTIVE = "INACTIVE"


class DocumentType(StrEnum):
    NIT = "NIT"
    CC = "CC"
    CE = "CE"
    PASSPORT = "PASSPORT"
    RUT = "RUT"
    OTHER = "OTHER"


@dataclass(kw_only=True)
class Company(BaseEntity):
    name: str
    legal_name: str | None = None
    document_type: DocumentType | None = None
    document_number: str | None = None
    email: str | None = None
    phone: str | None = None
    status: CompanyStatus = CompanyStatus.ACTIVE

    @property
    def is_operational(self) -> bool:
        """Only ACTIVE companies may be used as a tenant context."""
        return self.status is CompanyStatus.ACTIVE

    def suspend(self) -> None:
        self.status = CompanyStatus.SUSPENDED
        self.touch()

    def activate(self) -> None:
        self.status = CompanyStatus.ACTIVE
        self.touch()
