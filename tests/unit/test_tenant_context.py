from app.domain.authorization.permissions import (
    ALL_CODES,
    SYSTEM_ROLE_PERMISSIONS,
    WILDCARD,
    SystemRole,
)
from app.domain.shared.entities import new_id
from app.domain.tenants.tenant_context import TenantContext


def _ctx(role: SystemRole) -> TenantContext:
    return TenantContext(
        company_id=new_id(),
        user_id=new_id(),
        role_code=role.value,
        permissions=SYSTEM_ROLE_PERMISSIONS[role],
        role_id=new_id(),
    )


def test_owner_has_every_permission():
    assert _ctx(SystemRole.OWNER).has_permission("anything.at.all")


def test_seller_cannot_create_products():
    seller = _ctx(SystemRole.SELLER)
    assert seller.has_permission("products.read")
    assert not seller.has_permission("products.create")


def test_inventory_manager_can_adjust_but_not_manage_members():
    manager = _ctx(SystemRole.INVENTORY_MANAGER)
    assert manager.has_permission("inventory.adjust")
    assert not manager.has_permission("members.manage")


def test_admin_has_everything_except_the_wildcard():
    admin = _ctx(SystemRole.ADMIN)
    assert WILDCARD not in admin.permissions
    assert admin.has_permission("members.manage")
    assert admin.has_permission("reports.read")


def test_a_platform_admin_context_is_unrestricted_but_still_single_tenant():
    company_id = new_id()
    context = TenantContext.for_platform_admin(company_id=company_id, user_id=new_id())

    assert context.is_platform_admin
    assert context.has_permission("sales.cancel")
    assert context.company_id == company_id, "an operator still acts inside one company"


def test_every_system_role_grants_only_catalogued_permissions():
    """A typo in a role's grant list would silently disable an endpoint."""
    for role, permissions in SYSTEM_ROLE_PERMISSIONS.items():
        unknown = permissions - ALL_CODES
        assert unknown == frozenset(), f"{role.value} grants unknown permissions: {unknown}"
