"""The permission catalogue: the single source of truth.

Migration 0008 seeds the `permissions` table from this module, routers name
these codes in `require_permission(...)`, and a test asserts the two never
drift apart. Adding a permission means adding it here and granting it to the
roles that should have it.
"""

from dataclasses import dataclass
from enum import StrEnum

# A role holding this can do anything inside its company. Only OWNER has it.
WILDCARD = "*"


class SystemRole(StrEnum):
    """Roles every company gets for free. Companies may add their own on top."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    SELLER = "SELLER"
    INVENTORY_MANAGER = "INVENTORY_MANAGER"


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    code: str
    module: str
    description: str


CATALOG: tuple[PermissionDefinition, ...] = (
    PermissionDefinition(WILDCARD, "system", "Full access inside the company"),
    PermissionDefinition("company.read", "company", "View company details"),
    PermissionDefinition("company.update", "company", "Edit company details"),
    PermissionDefinition("members.read", "company", "List company members"),
    PermissionDefinition("members.manage", "company", "Add, update and remove members"),
    PermissionDefinition("roles.read", "company", "List roles and their permissions"),
    PermissionDefinition("roles.manage", "company", "Create and edit custom roles"),
    PermissionDefinition("categories.read", "catalog", "View categories"),
    PermissionDefinition("categories.write", "catalog", "Create and edit categories"),
    PermissionDefinition("products.read", "catalog", "View products"),
    PermissionDefinition("products.create", "catalog", "Create products"),
    PermissionDefinition("products.update", "catalog", "Edit products"),
    PermissionDefinition("products.delete", "catalog", "Deactivate products"),
    PermissionDefinition("warehouses.read", "inventory", "View warehouses"),
    PermissionDefinition("warehouses.write", "inventory", "Create and edit warehouses"),
    PermissionDefinition("inventory.read", "inventory", "View stock and movements"),
    PermissionDefinition("inventory.adjust", "inventory", "Adjust stock manually"),
    PermissionDefinition("inventory.transfer", "inventory", "Transfer stock between warehouses"),
    PermissionDefinition("customers.read", "partners", "View customers"),
    PermissionDefinition("customers.write", "partners", "Create and edit customers"),
    PermissionDefinition("suppliers.read", "partners", "View suppliers"),
    PermissionDefinition("suppliers.write", "partners", "Create and edit suppliers"),
    PermissionDefinition("credit.read", "credit", "Ver saldos de fiado"),
    PermissionDefinition("credit.manage", "credit", "Registrar abonos y ajustar cuentas"),
    PermissionDefinition("sales.read", "sales", "View sales"),
    PermissionDefinition("sales.create", "sales", "Create and complete sales"),
    PermissionDefinition("sales.cancel", "sales", "Cancel and refund sales"),
    PermissionDefinition("purchases.read", "purchases", "View purchases"),
    PermissionDefinition("purchases.create", "purchases", "Create and complete purchases"),
    PermissionDefinition("purchases.cancel", "purchases", "Cancel purchases"),
    PermissionDefinition("imports.read", "imports", "View imports and their errors"),
    PermissionDefinition("imports.run", "imports", "Upload files and load them into the company"),
    PermissionDefinition("files.read", "files", "View and download attachments"),
    PermissionDefinition("files.write", "files", "Upload and delete attachments"),
    PermissionDefinition("reports.read", "reports", "View reports"),
    PermissionDefinition("audit.read", "audit", "Read the audit log"),
)

ALL_CODES: frozenset[str] = frozenset(item.code for item in CATALOG)

# What each system role starts with. Companies can clone a role and adjust it.
SYSTEM_ROLE_PERMISSIONS: dict[SystemRole, frozenset[str]] = {
    SystemRole.OWNER: frozenset({WILDCARD}),
    SystemRole.ADMIN: ALL_CODES - {WILDCARD},
    SystemRole.INVENTORY_MANAGER: frozenset(
        {
            "company.read",
            "categories.read",
            "categories.write",
            "products.read",
            "products.create",
            "products.update",
            "warehouses.read",
            "warehouses.write",
            "inventory.read",
            "inventory.adjust",
            "inventory.transfer",
            "customers.read",
            "suppliers.read",
            "suppliers.write",
            "sales.read",
            "credit.read",
            "purchases.read",
            "purchases.create",
            "purchases.cancel",
            "files.read",
            "files.write",
            "imports.read",
            "imports.run",
            "reports.read",
        }
    ),
    SystemRole.SELLER: frozenset(
        {
            "company.read",
            "categories.read",
            "products.read",
            "warehouses.read",
            "inventory.read",
            "customers.read",
            "customers.write",
            "sales.read",
            "sales.create",
            # El vendedor fía y recibe abonos: es el mostrador.
            "credit.read",
            "credit.manage",
            "files.read",
            "imports.read",
        }
    ),
}

SYSTEM_ROLE_NAMES: dict[SystemRole, str] = {
    SystemRole.OWNER: "Owner",
    SystemRole.ADMIN: "Administrator",
    SystemRole.SELLER: "Seller",
    SystemRole.INVENTORY_MANAGER: "Inventory manager",
}
