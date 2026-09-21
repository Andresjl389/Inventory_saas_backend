"""Roles live in the database, so a company can define its own without a deploy."""

from tests.api.helpers import create_product, headers, login, register, tenant
from tests.conftest import requires_db

pytestmark = requires_db


async def _member_with_role(client, owner_headers, company_id, email, role_code) -> dict[str, str]:
    await register(client, email)
    invited = await client.post(
        "/api/v1/companies/current/members",
        headers=owner_headers,
        json={"email": email, "role": role_code},
    )
    assert invited.status_code == 201, invited.text
    return headers(await login(client, email), company_id)


async def test_the_built_in_roles_are_listed_with_their_permissions(client, engine, unique_email):
    owner, _ = await tenant(client, engine, unique_email)

    roles = await client.get("/api/v1/roles", headers=owner)

    by_code = {role["code"]: role for role in roles.json()}
    assert {"OWNER", "ADMIN", "SELLER", "INVENTORY_MANAGER"} <= set(by_code)
    assert all(role["is_system"] for role in by_code.values())
    assert by_code["OWNER"]["permissions"] == ["*"]
    assert "products.create" not in by_code["SELLER"]["permissions"]


async def test_a_company_can_create_a_role_and_it_is_enforced(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)

    created = await client.post(
        "/api/v1/roles",
        headers=owner,
        json={
            "code": "cashier",
            "name": "Cashier",
            "permissions": ["company.read", "products.read", "sales.read", "sales.create"],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "CASHIER"
    assert created.json()["is_system"] is False

    cashier = await _member_with_role(client, owner, company_id, "cashier@example.com", "CASHIER")

    assert (await client.get("/api/v1/products", headers=cashier)).status_code == 200
    assert (await client.get("/api/v1/sales", headers=cashier)).status_code == 200

    forbidden = await client.get("/api/v1/customers", headers=cashier)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["details"]["required_permission"] == "customers.read"


async def test_editing_a_role_changes_what_its_members_can_do(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)
    role = await client.post(
        "/api/v1/roles",
        headers=owner,
        json={"code": "CASHIER", "name": "Cashier", "permissions": ["company.read"]},
    )
    role_id = role.json()["id"]
    cashier = await _member_with_role(client, owner, company_id, "cashier@example.com", "CASHIER")
    assert (await client.get("/api/v1/products", headers=cashier)).status_code == 403

    await client.patch(
        f"/api/v1/roles/{role_id}",
        headers=owner,
        json={"permissions": ["company.read", "products.read"]},
    )

    # No re-login needed: permissions are read from the database per request.
    assert (await client.get("/api/v1/products", headers=cashier)).status_code == 200


async def test_built_in_roles_cannot_be_edited_by_a_company(client, engine, unique_email):
    owner, _ = await tenant(client, engine, unique_email)
    roles = (await client.get("/api/v1/roles", headers=owner)).json()
    seller_id = next(role["id"] for role in roles if role["code"] == "SELLER")

    response = await client.patch(
        f"/api/v1/roles/{seller_id}", headers=owner, json={"permissions": ["*"]}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SYSTEM_ROLE_IMMUTABLE"


async def test_an_unknown_permission_code_is_rejected(client, engine, unique_email):
    owner, _ = await tenant(client, engine, unique_email)

    response = await client.post(
        "/api/v1/roles",
        headers=owner,
        json={"code": "TYPO", "name": "Typo", "permissions": ["products.reed"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_PERMISSION"
    assert response.json()["error"]["details"]["unknown"] == ["products.reed"]


async def test_only_an_owner_can_mint_a_role_with_full_access(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)
    admin = await _member_with_role(client, owner, company_id, "admin@example.com", "ADMIN")

    escalation = await client.post(
        "/api/v1/roles",
        headers=admin,
        json={"code": "SUPER", "name": "Super", "permissions": ["*"]},
    )

    assert escalation.status_code == 422
    assert escalation.json()["error"]["code"] == "CANNOT_GRANT_WILDCARD"

    allowed = await client.post(
        "/api/v1/roles",
        headers=owner,
        json={"code": "SUPER", "name": "Super", "permissions": ["*"]},
    )
    assert allowed.status_code == 201


async def test_a_role_still_in_use_cannot_be_deleted(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)
    role = await client.post(
        "/api/v1/roles",
        headers=owner,
        json={"code": "CASHIER", "name": "Cashier", "permissions": ["company.read"]},
    )
    role_id = role.json()["id"]
    await _member_with_role(client, owner, company_id, "cashier@example.com", "CASHIER")

    response = await client.delete(f"/api/v1/roles/{role_id}", headers=owner)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROLE_IN_USE"


async def test_a_custom_role_belongs_to_one_company_only(client, engine):
    owner_a, _ = await tenant(client, engine, "a@example.com", "Acme")
    owner_b, _ = await tenant(client, engine, "b@example.com", "Globex")
    await client.post(
        "/api/v1/roles",
        headers=owner_a,
        json={"code": "CASHIER", "name": "Cashier", "permissions": ["company.read"]},
    )

    codes_b = {role["code"] for role in (await client.get("/api/v1/roles", headers=owner_b)).json()}

    assert "CASHIER" not in codes_b


async def test_changing_a_members_role_takes_effect_immediately(client, engine, unique_email):
    owner, company_id = await tenant(client, engine, unique_email)
    seller = await _member_with_role(client, owner, company_id, "s@example.com", "SELLER")
    await create_product(client, owner)
    assert (
        await client.post("/api/v1/products", headers=seller, json={"name": "X", "sku": "X-1"})
    ).status_code == 403

    users = (await client.get("/api/v1/companies/current/members", headers=owner)).json()
    seller_user_id = next(m["user_id"] for m in users if m["email"] == "s@example.com")

    promoted = await client.patch(
        f"/api/v1/companies/current/members/{seller_user_id}",
        headers=owner,
        json={"role": "ADMIN"},
    )
    assert promoted.json()["role"] == "ADMIN"

    assert (
        await client.post("/api/v1/products", headers=seller, json={"name": "X", "sku": "X-1"})
    ).status_code == 201


async def test_you_cannot_change_your_own_role(client, engine, unique_email):
    owner, _ = await tenant(client, engine, unique_email)
    me = (await client.get("/api/v1/auth/me", headers=owner)).json()

    response = await client.patch(
        f"/api/v1/companies/current/members/{me['id']}", headers=owner, json={"role": "SELLER"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CANNOT_CHANGE_OWN_ROLE"
