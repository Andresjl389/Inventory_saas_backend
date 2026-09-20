from dataclasses import dataclass

from app.domain.shared.entities import TenantEntity


@dataclass(kw_only=True)
class Warehouse(TenantEntity):
    name: str
    address: str | None = None
    is_active: bool = True

    def rename(self, name: str) -> None:
        self.name = name
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()
