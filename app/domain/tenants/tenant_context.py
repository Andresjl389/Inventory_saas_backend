"""The resolved tenant for the current request.

Built by the presentation layer *after* confirming the authenticated user holds
an active membership in the requested company. It is the only thing the
application layer may trust when scoping data.

The permission set is loaded from the database (roles -> role_permissions), so
a company that defines its own role gets it enforced without a deploy.
"""

import uuid
from dataclasses import dataclass, field

from app.domain.authorization.permissions import WILDCARD

PLATFORM_ADMIN_ROLE = "PLATFORM_ADMIN"


@dataclass(frozen=True, slots=True)
class TenantContext:
    company_id: uuid.UUID
    user_id: uuid.UUID
    role_code: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    role_id: uuid.UUID | None = None
    # True when a platform superuser stepped into this company. They are not a
    # member, so there is no role row behind them.
    is_platform_admin: bool = False

    def has_permission(self, permission: str) -> bool:
        return WILDCARD in self.permissions or permission in self.permissions

    @classmethod
    def for_platform_admin(cls, *, company_id: uuid.UUID, user_id: uuid.UUID) -> "TenantContext":
        return cls(
            company_id=company_id,
            user_id=user_id,
            role_code=PLATFORM_ADMIN_ROLE,
            permissions=frozenset({WILDCARD}),
            is_platform_admin=True,
        )
