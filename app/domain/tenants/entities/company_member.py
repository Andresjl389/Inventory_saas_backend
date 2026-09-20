"""Membership linking a user to a company, carrying the role they hold there.

The role is a row in `roles`, not an enum: companies can define their own on
top of the system ones. `role_code` is carried alongside the id purely so
callers can display and compare without a second lookup.
"""

import uuid
from dataclasses import dataclass

from app.domain.shared.entities import BaseEntity


@dataclass(kw_only=True)
class CompanyMember(BaseEntity):
    company_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    role_code: str = ""
    is_active: bool = True

    def change_role(self, role_id: uuid.UUID, role_code: str) -> None:
        self.role_id = role_id
        self.role_code = role_code
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()
