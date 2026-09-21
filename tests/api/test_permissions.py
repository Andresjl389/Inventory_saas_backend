"""Role-based authorization: the layer above RLS.

RLS stops one tenant reading another's data; it says nothing about what a
SELLER may do inside their own company. That is what require_permission covers.
"""

from tests.api.helpers import (
    create_product,
    create_warehouse,
    headers,
    login,
    register,
    tenant,
)
from tests.conftest import requires_db

pytestmark = requires_db


async def _member_with_role(client, owner_headers, company_id, email, role) -> dict[str, str]:
    await register(client, email)
    invited = await client.post(
        "/api/v1/companies/current/members",
        headers=owner_headers,
        json={"email": email, "role": role},
    )
    assert invited.status_code == 201, invited.text
    return headers(await login(client, email), company_id)


async def test_a_seller_can_sell_but_not_adjust_inventory(client, engine):
    owner_headers, company_id = await tenant(client, engine, "owner@example.com")
    warehouse_id = await create_warehouse(client, owner_headers)
    product_id = await create_product(client, owner_headers)

    seller = await _member_with_role(
        client, owner_headers, company_id, "seller@example.com", "SELLER"
    )

    assert (await client.get("/api/v1/products", headers=seller)).status_code == 200
    assert (await client.get("/api/v1/sales", headers=seller)).status_code == 200

    forbidden = await client.post(
        "/api/v1/inventory/adjustments",
        headers=seller,
        json={"product_id": product_id, "warehouse_id": warehouse_id, "quantity_delta": "5"},
    )
    assert forbidden.status_code == 403
    body = forbidden.json()["error"]
    assert body["code"] == "INSUFFICIENT_ROLE"
    assert body["details"]["required_permission"] == "inventory.adjust"


async def test_a_seller_cannot_create_products_or_manage_members(client, engine):
    owner_headers, company_id = await tenant(client, engine, "owner@example.com")
    seller = await _member_with_role(
        client, owner_headers, company_id, "seller@example.com", "SELLER"
    )

    created = await client.post(
        "/api/v1/products", headers=seller, json={"name": "Hammer", "sku": "HMR-1"}
    )
    assert created.status_code == 403

    members = await client.get("/api/v1/companies/current/members", headers=seller)
    assert members.status_code == 403


async def test_an_inventory_manager_can_adjust_but_not_sell(client, engine):
    owner_headers, company_id = await tenant(client, engine, "owner@example.com")
    warehouse_id = await create_warehouse(client, owner_headers)
    product_id = await create_product(client, owner_headers)

    manager = await _member_with_role(
        client, owner_headers, company_id, "wm@example.com", "INVENTORY_MANAGER"
    )

    adjusted = await client.post(
        "/api/v1/inventory/adjustments",
        headers=manager,
        json={"product_id": product_id, "warehouse_id": warehouse_id, "quantity_delta": "5"},
    )
    assert adjusted.status_code == 200, adjusted.text

    sold = await client.post(
        "/api/v1/sales",
        headers=manager,
        json={
            "warehouse_id": warehouse_id,
            "items": [{"product_id": product_id, "quantity": "1"}],
        },
    )
    assert sold.status_code == 403
    assert sold.json()["error"]["details"]["required_permission"] == "sales.create"


async def test_a_member_of_one_company_cannot_use_another(client, engine):
    owner_headers, company_id = await tenant(client, engine, "owner@example.com", "Acme")
    _, other_company_id = await tenant(client, engine, "other@example.com", "Globex")

    seller = await _member_with_role(
        client, owner_headers, company_id, "seller@example.com", "SELLER"
    )
    seller_token = seller["Authorization"].removeprefix("Bearer ")

    response = await client.get("/api/v1/products", headers=headers(seller_token, other_company_id))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_MEMBERSHIP"
