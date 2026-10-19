from dataclasses import dataclass
from decimal import Decimal

from app.domain.shared.document import DocumentType
from app.domain.shared.entities import TenantEntity


@dataclass(kw_only=True)
class Customer(TenantEntity):
    name: str
    document_type: DocumentType | None = None
    document_number: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    is_active: bool = True
    # Tope de fiado. 0 = sin tope, igual que los límites de los planes: "sin
    # límite" es un valor real y un NULL habría que tratarlo aparte en cada
    # comparación.
    credit_limit: Decimal = Decimal("0")

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()
