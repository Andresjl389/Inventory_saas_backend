"""Roles.

A role with `company_id = None` is a *system* role: it exists for every company
and only the platform admin may edit it. A role with a company_id is that
company's own, and its members manage it.
"""

import uuid
from dataclasses import dataclass, field

from app.domain.authorization.permissions import WILDCARD
from app.domain.shared.entities import BaseEntity


@dataclass(kw_only=True)
class Role(BaseEntity):
    code: str
    name: str
    company_id: uuid.UUID | None = None
    description: str | None = None
    is_system: bool = False
    permissions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        self.code = self.code.strip().upper().replace(" ", "_")

    @property
    def is_custom(self) -> bool:
        return self.company_id is not None

    def grants(self, permission: str) -> bool:
        return WILDCARD in self.permissions or permission in self.permissions

    def replace_permissions(self, permissions: frozenset[str]) -> None:
        self.permissions = permissions
        self.touch()


@dataclass(frozen=True, slots=True)
class Permission:
    id: uuid.UUID
    code: str
    module: str
    description: str
