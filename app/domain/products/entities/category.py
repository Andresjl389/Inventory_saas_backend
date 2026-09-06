import uuid
from dataclasses import dataclass

from app.domain.shared.entities import TenantEntity


@dataclass(kw_only=True)
class Category(TenantEntity):
    name: str
    description: str | None = None

    def rename(self, name: str) -> None:
        self.name = name
        self.touch()

    def belongs_to(self, company_id: uuid.UUID) -> bool:
        return self.company_id == company_id
