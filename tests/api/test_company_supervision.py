"""Supervising companies, and loading a whole one from a workbook."""

from decimal import Decimal

from tests.api.helpers import (
    XLSX_MEDIA_TYPE,
    create_product,
    create_warehouse,
    platform_admin,
    receive_stock,
    tenant,
    workbook_bytes,
)
from tests.conftest import requires_db

pytestmark = requires_db


async def _company_with_activity(client, email: str, name: str) -> tuple[dict, str]:
    hdrs, company_id = await tenant(client, email, name)
    warehouse_id = await create_warehouse(client, hdrs)
    product_id = await create_product(client, hdrs, sale_price="20.00", cost_price="8.00")
    await receive_stock(client, hdrs, product_id, warehouse_id, "10")
    await client.post(
        "/api/v1/sales",
        headers=hdrs,
        json={
            "warehouse_id": warehouse_id,
            "complete": True,
            "items": [{"product_id": product_id, "quantity": "2"}],
        },
    )
    return hdrs, company_id


async def test_the_supervision_table_shows_live_numbers_per_company(client, engine):
    admin = await platform_admin(client, engine)
    await _company_with_activity(client, "a@example.com", "Acme")
    await tenant(client, "b@example.com", "Quiet Co")

    response = await client.get(
        "/api/v1/admin/companies/supervision", headers=admin, params={"with_metrics": "true"}
    )

    assert response.status_code == 200, response.text
    rows = {item["company"]["name"]: item for item in response.json()["items"]}
    assert {"Acme", "Quiet Co"} <= set(rows)

    acme = rows["Acme"]["metrics"]
    assert acme["products"] == 1
    assert acme["warehouses"] == 1
    assert acme["sales_count"] == 1
    assert Decimal(acme["sales_revenue"]) == Decimal("40")
    assert Decimal(acme["stock_value"]) == Decimal("64"), "8 units at cost 8"

    assert rows["Quiet Co"]["metrics"]["sales_count"] == 0


async def test_the_fast_listing_skips_the_per_company_queries(client, engine, unique_email):
    admin = await platform_admin(client, engine)
    await tenant(client, unique_email)

    response = await client.get(
        "/api/v1/admin/companies/supervision", headers=admin, params={"with_metrics": "false"}
    )

    assert response.json()["items"][0]["metrics"] is None


async def test_company_overview_reports_usage_against_the_plan(client, engine):
    admin = await platform_admin(client, engine)
    _, company_id = await _company_with_activity(client, "a@example.com", "Acme")
    await client.put(
        f"/api/v1/admin/companies/{company_id}/subscription",
        headers=admin,
        json={"plan_code": "FREE", "status": "ACTIVE"},
    )

    overview = (
        await client.get(f"/api/v1/admin/companies/{company_id}/overview", headers=admin)
    ).json()

    assert overview["company"]["name"] == "Acme"
    assert overview["plan"]["code"] == "FREE"
    assert overview["metrics"]["active_members"] == 1
    assert overview["days_since_last_sale"] == 0

    usage = {item["resource"]: item for item in overview["usage"]}
    assert usage["warehouses"]["used"] == 1
    assert usage["warehouses"]["limit"] == 1
    assert usage["warehouses"]["over_limit"] is False
    assert usage["products"]["limit"] == 50


async def test_the_overview_never_mixes_two_companies(client, engine):
    admin = await platform_admin(client, engine)
    _, company_a = await _company_with_activity(client, "a@example.com", "Acme")
    _, company_b = await tenant(client, "b@example.com", "Globex")

    a = (await client.get(f"/api/v1/admin/companies/{company_a}/overview", headers=admin)).json()
    b = (await client.get(f"/api/v1/admin/companies/{company_b}/overview", headers=admin)).json()

    assert a["metrics"]["products"] == 1
    assert b["metrics"]["products"] == 0
    assert b["metrics"]["sales_count"] == 0


async def test_a_normal_member_cannot_reach_supervision(client, engine, unique_email):
    member, company_id = await tenant(client, unique_email)

    for path in (
        "/api/v1/admin/companies/supervision",
        f"/api/v1/admin/companies/{company_id}/overview",
    ):
        response = await client.get(path, headers=member)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "NOT_PLATFORM_ADMIN"


async def test_the_onboarding_template_has_a_sheet_per_entity(client, engine):
    admin = await platform_admin(client, engine)

    response = await client.get("/api/v1/admin/onboarding/template", headers=admin)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(XLSX_MEDIA_TYPE)

    from app.infrastructure.imports.reader import read_all_sheets

    sheets = read_all_sheets(response.content)
    assert {
        "Categorías",
        "Bodegas",
        "Productos",
        "Clientes",
        "Proveedores",
        "Stock inicial",
    } <= set(sheets)


async def test_an_operator_loads_a_whole_company_from_one_workbook(client, engine, unique_email):
    admin = await platform_admin(client, engine)
    _, company_id = await tenant(client, unique_email, "Nueva Empresa")

    payload = workbook_bytes(
        [],
        sheets={
            "Categorías": [["Nombre"], ["Herramientas"]],
            "Bodegas": [["Nombre", "Dirección"], ["Bodega Central", "Calle 1"]],
            "Productos": [
                ["Referencia", "Articulo", "Familia", "PVP", "Costo"],
                ["MAR-01", "Martillo", "Herramientas", "$ 15.000", "8.000"],
                ["DES-02", "Destornillador", "Herramientas", "9.500", "4.000"],
            ],
            "Clientes": [["Razón social", "NIT"], ["Cliente Uno", "900123"]],
            "Stock inicial": [
                ["Codigo", "Bodega", "Cantidad"],
                ["MAR-01", "Bodega Central", "30"],
            ],
        },
    )

    response = await client.post(
        f"/api/v1/admin/companies/{company_id}/onboarding",
        headers=admin,
        files={"file": ("carga.xlsx", payload, XLSX_MEDIA_TYPE)},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dry_run"] is False
    by_entity = {sheet["entity"]: sheet for sheet in body["sheets"]}
    assert by_entity["CATEGORIES"]["stats"]["created"] == 1
    assert by_entity["PRODUCTS"]["stats"]["created"] == 2
    assert by_entity["STOCK"]["stats"]["created"] == 1
    assert by_entity["SUPPLIERS"]["status"] == "SKIPPED", "a sheet nobody sent is skipped"

    # The company is usable straight away.
    hdrs = {**admin, "X-Company-ID": company_id}
    products = (await client.get("/api/v1/products", headers=hdrs)).json()
    assert products["total"] == 2
    stock = (await client.get("/api/v1/inventory/stock", headers=hdrs)).json()
    assert Decimal(stock["items"][0]["quantity"]) == Decimal("30")


async def test_onboarding_is_all_or_nothing(client, engine, unique_email):
    """A later sheet failing must not leave half a company behind."""
    admin = await platform_admin(client, engine)
    _, company_id = await tenant(client, unique_email, "Nueva Empresa")

    dry = await client.post(
        f"/api/v1/admin/companies/{company_id}/onboarding",
        headers=admin,
        params={"dry_run": "true"},
        files={
            "file": (
                "carga.xlsx",
                workbook_bytes(
                    [],
                    sheets={
                        "Categorías": [["Nombre"], ["Herramientas"]],
                        "Productos": [["Referencia", "Articulo"], ["MAR-01", "Martillo"]],
                    },
                ),
                XLSX_MEDIA_TYPE,
            )
        },
    )

    assert dry.json()["totals"]["created"] == 2
    hdrs = {**admin, "X-Company-ID": company_id}
    assert (await client.get("/api/v1/products", headers=hdrs)).json()["total"] == 0
    assert (await client.get("/api/v1/categories", headers=hdrs)).json() == []


async def test_a_sheet_missing_a_required_column_is_reported_not_guessed(
    client, engine, unique_email
):
    admin = await platform_admin(client, engine)
    _, company_id = await tenant(client, unique_email, "Nueva Empresa")

    response = await client.post(
        f"/api/v1/admin/companies/{company_id}/onboarding",
        headers=admin,
        params={"dry_run": "true"},
        files={
            "file": (
                "carga.xlsx",
                workbook_bytes([], sheets={"Productos": [["Articulo"], ["Martillo"]]}),
                XLSX_MEDIA_TYPE,
            )
        },
    )

    sheet = next(s for s in response.json()["sheets"] if s["entity"] == "PRODUCTS")
    assert sheet["status"] == "MISSING_COLUMNS"
    assert sheet["missing_required"] == ["sku"]
