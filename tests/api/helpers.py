"""Shared HTTP helpers for the API tests."""

from decimal import Decimal

PASSWORD = "sup3r-secret-pw"


async def register(client, email: str, company: str | None = "Acme") -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company_name": company,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login(client, email: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def headers(token: str, company_id: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {token}"}
    if company_id:
        result["X-Company-ID"] = company_id
    return result


async def tenant(client, email: str, company: str = "Acme") -> tuple[dict[str, str], str]:
    """Register + log in, returning ready-to-use headers and the company id."""
    body = await register(client, email, company)
    token = await login(client, email)
    company_id = body["company_id"]
    return headers(token, company_id), company_id


async def create_warehouse(client, hdrs: dict, name: str = "Main") -> str:
    response = await client.post("/api/v1/warehouses", headers=hdrs, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def create_product(client, hdrs: dict, sku: str = "SKU-1", **fields) -> str:
    """Extra keyword arguments go straight into the payload (cost_price,
    sale_price, min_stock, category_id...)."""
    payload = {"name": fields.pop("name", "Hammer"), "sku": sku, **fields}
    response = await client.post("/api/v1/products", headers=hdrs, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def stock_of(client, hdrs: dict, product_id: str, warehouse_id: str) -> Decimal:
    response = await client.get(
        "/api/v1/inventory/stock",
        headers=hdrs,
        params={"product_id": product_id, "warehouse_id": warehouse_id},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    return Decimal(items[0]["quantity"]) if items else Decimal("0")


async def receive_stock(
    client, hdrs: dict, product_id: str, warehouse_id: str, quantity: str
) -> None:
    """Put stock in through a completed purchase -- the realistic way."""
    response = await client.post(
        "/api/v1/purchases",
        headers=hdrs,
        json={
            "warehouse_id": warehouse_id,
            "complete": True,
            "items": [{"product_id": product_id, "quantity": quantity, "unit_cost": "1.00"}],
        },
    )
    assert response.status_code == 201, response.text


async def platform_admin(client, engine, email: str = "ops@example.com") -> dict[str, str]:
    """Create a platform administrator and return its auth headers.

    `is_superuser` is set directly in the database because that is the only way
    it is ever set: there is no API that promotes the first operator, only the
    `create-superuser` CLI.
    """
    from sqlalchemy import text

    await register(client, email, company=None)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET is_superuser = true WHERE email = :email"),
            {"email": email},
        )
    return headers(await login(client, email))


async def as_company(admin_headers: dict[str, str], company_id: str) -> dict[str, str]:
    """An operator stepping into one company: same headers plus X-Company-ID."""
    return {**admin_headers, "X-Company-ID": company_id}
