"""Product endpoints, including cross-tenant access through the real HTTP stack."""

from tests.api.helpers import tenant as _tenant
from tests.conftest import requires_db

pytestmark = requires_db


async def test_create_and_list_products(client, unique_email):
    headers, _ = await _tenant(client, unique_email, "Acme")

    category = await client.post("/api/v1/categories", headers=headers, json={"name": "Tools"})
    assert category.status_code == 201

    created = await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "name": "Hammer",
            "sku": "hmr-01",
            "category_id": category.json()["id"],
            "cost_price": "10.5000",
            "sale_price": "19.9900",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["sku"] == "HMR-01"

    listing = await client.get("/api/v1/products", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


async def test_duplicate_sku_within_a_company_is_rejected(client, unique_email):
    headers, _ = await _tenant(client, unique_email, "Acme")
    payload = {"name": "Hammer", "sku": "HMR-01"}

    assert (await client.post("/api/v1/products", headers=headers, json=payload)).status_code == 201
    duplicate = await client.post("/api/v1/products", headers=headers, json=payload)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_SKU"


async def test_the_same_sku_is_fine_in_a_different_company(client):
    headers_a, _ = await _tenant(client, "a@example.com", "Acme")
    headers_b, _ = await _tenant(client, "b@example.com", "Globex")
    payload = {"name": "Hammer", "sku": "HMR-01"}

    first = await client.post("/api/v1/products", headers=headers_a, json=payload)
    second = await client.post("/api/v1/products", headers=headers_b, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201


async def test_a_product_is_invisible_to_another_tenant(client):
    headers_a, _ = await _tenant(client, "a@example.com", "Acme")
    headers_b, _ = await _tenant(client, "b@example.com", "Globex")

    created = await client.post(
        "/api/v1/products",
        headers=headers_a,
        json={"name": "Hammer", "sku": "HMR-01"},
    )
    product_id = created.json()["id"]

    # B is authenticated and inside its own valid tenant -- the product simply
    # does not exist as far as B is concerned.
    response = await client.get(f"/api/v1/products/{product_id}", headers=headers_b)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"

    listing = await client.get("/api/v1/products", headers=headers_b)
    assert listing.json()["total"] == 0


async def test_deactivating_a_product_keeps_the_row(client, unique_email):
    headers, _ = await _tenant(client, unique_email, "Acme")
    created = await client.post(
        "/api/v1/products", headers=headers, json={"name": "Hammer", "sku": "HMR-01"}
    )
    product_id = created.json()["id"]

    response = await client.delete(f"/api/v1/products/{product_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert (await client.get(f"/api/v1/products/{product_id}", headers=headers)).status_code == 200
