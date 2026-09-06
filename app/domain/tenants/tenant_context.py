"""The resolved tenant for the current request.

Built by the presentation layer *after* validating that the authenticated user
holds an active membership in the requested company. It is the only thing the
application layer is allowed to trust when scoping data.
"""

import uuid
from dataclasses import dataclass

from app.domain.tenants.entities.company_member import CompanyRole

# Role -> permissions. Kept in code for the first version; section 10 of
# BACKEND.md describes the evolution towards roles/permissions tables.
ROLE_PERMISSIONS: dict[CompanyRole, frozenset[str]] = {
    CompanyRole.OWNER: frozenset({"*"}),
    CompanyRole.ADMIN: frozenset(
        {
            "company.read",
            "company.update",
            "members.read",
            "members.manage",
            "categories.read",
            "categories.write",
            "products.read",
            "products.create",
            "products.update",
            "products.delete",
            "warehouses.read",
            "warehouses.write",
            "inventory.read",
            "inventory.adjust",
            "inventory.transfer",
        }
    ),
    CompanyRole.INVENTORY_MANAGER: frozenset(
        {
            "company.read",
            "categories.read",
            "categories.write",
            "products.read",
            "products.create",
            "products.update",
            "warehouses.read",
            "inventory.read",
            "inventory.adjust",
            "inventory.transfer",
        }
    ),
    CompanyRole.SELLER: frozenset(
        {
            "company.read",
            "categories.read",
            "products.read",
            "warehouses.read",
            "inventory.read",
        }
    ),
}


@dataclass(frozen=True, slots=True)
class TenantContext:
    company_id: uuid.UUID
    user_id: uuid.UUID
    role: CompanyRole

    @property
    def permissions(self) -> frozenset[str]:
        return ROLE_PERMISSIONS.get(self.role, frozenset())

    def has_permission(self, permission: str) -> bool:
        perms = self.permissions
        return "*" in perms or permission in perms
