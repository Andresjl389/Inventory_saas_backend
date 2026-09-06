"""Membership linking a user to a company, carrying that user's role there."""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.domain.shared.entities import BaseEntity


class CompanyRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    SELLER = "SELLER"
    INVENTORY_MANAGER = "INVENTORY_MANAGER"


@dataclass(kw_only=True)
class CompanyMember(BaseEntity):
    company_id: uuid.UUID
    user_id: uuid.UUID
    role: CompanyRole
    is_active: bool = True

    def change_role(self, role: CompanyRole) -> None:
        self.role = role
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()
