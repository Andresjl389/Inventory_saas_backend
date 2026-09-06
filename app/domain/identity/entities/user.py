"""User entity.

A user is *not* tenant-scoped: the same person can belong to several companies
through `CompanyMember`.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.shared.entities import BaseEntity, utc_now


@dataclass(kw_only=True)
class User(BaseEntity):
    email: str
    password_hash: str
    first_name: str
    last_name: str
    is_active: bool = True
    is_superuser: bool = False
    last_login_at: datetime | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def change_password(self, new_hash: str) -> None:
        self.password_hash = new_hash
        self.touch()

    def register_login(self) -> None:
        self.last_login_at = utc_now()
        self.touch()
