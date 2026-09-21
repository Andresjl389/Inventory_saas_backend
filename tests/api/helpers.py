"""Shared HTTP helpers for the API tests."""

from decimal import Decimal

PASSWORD = "sup3r-secret-pw"
PLATFORM_ADMIN_EMAIL = "ops@example.com"


async def register(client, email: str) -> dict:
    """Create an account. It belongs to no company -- that is the whole point:
    signing up can no longer conjure a tenant."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Ada",
            "last_name": "Lovelace",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login(client, email: str, password: str = PASSWORD) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def headers(token: str, company_id: str | None = None) -> dict[str, str]:
    result = {"Authorization": f"Bearer {token}"}
    if company_id:
        result["X-Company-ID"] = company_id
    return result


async def platform_admin(client, engine, email: str = PLATFORM_ADMIN_EMAIL) -> dict[str, str]:
    """Create (once) a platform administrator and return its auth headers.

    `is_superuser` is set straight in the database because that is the only way
    it is ever set: no API promotes the first operator, only the
    `create-superuser` CLI. Idempotent, so a test may ask for it more than once.
    """
    from sqlalchemy import text

    existing = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Ops",
            "last_name": "Admin",
        },
    )
    assert existing.status_code in (201, 409), existing.text

    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET is_superuser = true WHERE email = :email"),
            {"email": email},
        )
    return headers(await login(client, email))


async def provision_company(
    client, engine, *, name: str, owner_email: str, plan_code: str | None = None
) -> dict:
    """The only way a company comes into being: an operator creates it and
    names its owner in the same call."""
    admin = await platform_admin(client, engine)
    payload = {
        "name": name,
        "owner_email": owner_email,
        "owner_password": PASSWORD,
        "owner_first_name": "Ada",
        "owner_last_name": "Lovelace",
    }
    if plan_code:
        payload["plan_code"] = plan_code

    response = await client.post("/api/v1/admin/companies", headers=admin, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def tenant(client, engine, email: str, company: str = "Acme") -> tuple[dict[str, str], str]:
    """A provisioned company plus its owner's ready-to-use headers."""
    provisioned = await provision_company(client, engine, name=company, owner_email=email)
    company_id = provisioned["company"]["id"]
    return headers(await login(client, email), company_id), company_id


async def add_member(client, owner_headers: dict, company_id: str, email: str, role: str) -> dict:
    """Attach somebody to a company the owner already administers, creating
    their account on the way in."""
    response = await client.post(
        "/api/v1/companies/current/members",
        headers=owner_headers,
        json={
            "email": email,
            "role": role,
            "password": PASSWORD,
            "first_name": "Team",
            "last_name": "Member",
        },
    )
    assert response.status_code == 201, response.text
    return headers(await login(client, email), company_id)


async def as_company(admin_headers: dict[str, str], company_id: str) -> dict[str, str]:
    """An operator stepping into one company: same headers plus X-Company-ID."""
    return {**admin_headers, "X-Company-ID": company_id}


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


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def upload(
    client,
    hdrs: dict,
    *,
    content: bytes = PNG_BYTES,
    filename: str = "photo.png",
    content_type: str = "image/png",
    owner_type: str = "COMPANY",
    owner_id: str | None = None,
):
    data = {"owner_type": owner_type}
    if owner_id:
        data["owner_id"] = owner_id
    return await client.post(
        "/api/v1/files",
        headers=hdrs,
        files={"file": (filename, content, content_type)},
        data=data,
    )


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def workbook_bytes(rows: list[list], sheets: dict[str, list[list]] | None = None) -> bytes:
    """Build an .xlsx in memory. `sheets` builds a multi-sheet workbook instead."""
    import io

    from openpyxl import Workbook

    book = Workbook()
    if sheets is None:
        sheet = book.active
        for row in rows:
            sheet.append(row)
    else:
        book.remove(book.active)
        for name, sheet_rows in sheets.items():
            sheet = book.create_sheet(name[:31])
            for row in sheet_rows:
                sheet.append(row)

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


async def start_import(client, hdrs: dict, *, entity: str, payload: bytes, filename="datos.xlsx"):
    return await client.post(
        "/api/v1/imports",
        headers=hdrs,
        files={"file": (filename, payload, XLSX_MEDIA_TYPE)},
        data={"entity": entity},
    )
