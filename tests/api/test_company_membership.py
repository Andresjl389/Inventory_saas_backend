"""Who belongs to which company, and who decides.

The model: a platform operator creates companies and names each one's owner;
that owner then runs their own team. Nobody conjures a company by typing a name
into a sign-up form, and membership is always against a company that already
exists, identified by its id.
"""

from tests.api.helpers import (
    PASSWORD,
    add_member,
    headers,
    login,
    platform_admin,
    provision_company,
    register,
    tenant,
)
from tests.conftest import requires_db

pytestmark = requires_db


async def test_provisioning_names_the_owner_who_then_runs_the_company(client, engine):
    """The company gets exactly one person who can manage roles and members."""
    await provision_company(
        client, engine, name="Ferretería Central", owner_email="ana@ferreteria.com"
    )
    owner = headers(await login(client, "ana@ferreteria.com"))

    companies = (await client.get("/api/v1/companies", headers=owner)).json()
    assert len(companies) == 1
    assert companies[0]["role"] == "OWNER"

    company_id = companies[0]["company_id"]
    scoped = headers(await login(client, "ana@ferreteria.com"), company_id)

    # Everything the owner needs to run the place.
    assert (
        await client.get("/api/v1/companies/current/members", headers=scoped)
    ).status_code == 200
    assert (await client.get("/api/v1/roles", headers=scoped)).status_code == 200
    assert (
        await client.post(
            "/api/v1/roles",
            headers=scoped,
            json={"code": "CAJERO", "name": "Cajero", "permissions": ["company.read"]},
        )
    ).status_code == 201


async def test_the_owner_onboards_their_own_team(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)

    invited = await client.post(
        "/api/v1/companies/current/members",
        headers=owner,
        json={
            "email": "vendedor@example.com",
            "role": "SELLER",
            "password": PASSWORD,
            "first_name": "Luis",
            "last_name": "Paz",
        },
    )

    assert invited.status_code == 201, invited.text
    assert invited.json()["role"] == "SELLER"

    # The new person can log in and lands in exactly that company.
    seller = headers(await login(client, "vendedor@example.com"))
    assert [
        c["company_id"] for c in (await client.get("/api/v1/companies", headers=seller)).json()
    ] == [company_id]


async def test_an_existing_account_is_attached_not_duplicated(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)
    await register(client, "existente@example.com")

    invited = await client.post(
        "/api/v1/companies/current/members",
        headers=owner,
        json={"email": "existente@example.com", "role": "ADMIN"},
    )

    assert invited.status_code == 201
    assert invited.json()["role"] == "ADMIN"


async def test_adding_an_unknown_email_without_a_password_says_what_is_missing(
    client, engine, unique_email
):
    owner, _ = await tenant(client, engine, unique_email)

    response = await client.post(
        "/api/v1/companies/current/members",
        headers=owner,
        json={"email": "nadie@example.com", "role": "SELLER"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ACCOUNT_DETAILS_REQUIRED"


async def test_a_seller_cannot_manage_the_team(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)
    seller = await add_member(client, owner, company_id, "vendedor@example.com", "SELLER")

    response = await client.post(
        "/api/v1/companies/current/members",
        headers=seller,
        json={
            "email": "otro@example.com",
            "role": "SELLER",
            "password": PASSWORD,
            "first_name": "Otro",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["details"]["required_permission"] == "members.manage"


async def test_an_operator_attaches_a_user_to_any_company_by_id(client, engine, unique_email):
    """This is the repair path: a company that lost its administrator."""
    admin = await platform_admin(client, engine)
    _, company_id = await tenant(client, engine, unique_email)
    await register(client, "rescate@example.com")

    attached = await client.post(
        f"/api/v1/admin/companies/{company_id}/members",
        headers=admin,
        json={"email": "rescate@example.com", "role": "ADMIN"},
    )

    assert attached.status_code == 201, attached.text
    assert attached.json()["role"] == "ADMIN"

    rescued = headers(await login(client, "rescate@example.com"), company_id)
    assert (
        await client.get("/api/v1/companies/current/members", headers=rescued)
    ).status_code == 200


async def test_an_operator_changes_a_members_role_in_any_company(client, engine, unique_email):
    admin = await platform_admin(client, engine)
    owner, company_id = await tenant(client, engine, unique_email)
    await add_member(client, owner, company_id, "vendedor@example.com", "SELLER")

    members = (await client.get("/api/v1/companies/current/members", headers=owner)).json()
    seller_id = next(m["user_id"] for m in members if m["email"] == "vendedor@example.com")

    changed = await client.patch(
        f"/api/v1/admin/companies/{company_id}/members/{seller_id}",
        headers=admin,
        json={"role": "INVENTORY_MANAGER"},
    )

    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "INVENTORY_MANAGER"

    seller = headers(await login(client, "vendedor@example.com"), company_id)
    assert (
        await client.post(
            "/api/v1/inventory/adjustments",
            headers=seller,
            json={"product_id": company_id, "warehouse_id": company_id, "quantity_delta": "1"},
        )
    ).status_code != 403, "the new role's permissions apply immediately"


async def test_a_member_cannot_reach_the_admin_membership_routes(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)

    response = await client.post(
        f"/api/v1/admin/companies/{company_id}/members",
        headers=owner,
        json={"email": "x@example.com", "role": "ADMIN"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_PLATFORM_ADMIN"


async def test_membership_is_recorded_in_the_audit_log(client, engine, unique_email):
    admin = await platform_admin(client, engine)
    _, company_id = await tenant(client, engine, unique_email)
    await register(client, "auditado@example.com")
    await client.post(
        f"/api/v1/admin/companies/{company_id}/members",
        headers=admin,
        json={"email": "auditado@example.com", "role": "ADMIN"},
    )

    log = await client.get("/api/v1/admin/audit", headers=admin, params={"action": "MEMBER_ADDED"})

    assert log.json()["total"] == 1
    assert log.json()["items"][0]["payload"]["email"] == "auditado@example.com"
