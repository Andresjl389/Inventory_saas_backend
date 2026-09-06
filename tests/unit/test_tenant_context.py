from app.domain.shared.entities import new_id
from app.domain.tenants.entities.company_member import CompanyRole
from app.domain.tenants.tenant_context import TenantContext


def _ctx(role: CompanyRole) -> TenantContext:
    return TenantContext(company_id=new_id(), user_id=new_id(), role=role)


def test_owner_has_every_permission():
    assert _ctx(CompanyRole.OWNER).has_permission("anything.at.all")


def test_seller_cannot_create_products():
    seller = _ctx(CompanyRole.SELLER)
    assert seller.has_permission("products.read")
    assert not seller.has_permission("products.create")


def test_inventory_manager_can_adjust_but_not_manage_members():
    manager = _ctx(CompanyRole.INVENTORY_MANAGER)
    assert manager.has_permission("inventory.adjust")
    assert not manager.has_permission("members.manage")
