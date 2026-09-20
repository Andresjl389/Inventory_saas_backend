from dataclasses import dataclass

from app.domain.shared.document import DocumentType
from app.domain.shared.entities import TenantEntity


@dataclass(kw_only=True)
class Supplier(TenantEntity):
    name: str
    document_type: DocumentType | None = None
    document_number: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    is_active: bool = True

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()
