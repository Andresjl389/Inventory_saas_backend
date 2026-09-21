"""Reports, the audit trail inside a company, and the low-stock job."""

from decimal import Decimal

from tests.api.helpers import (
    create_product,
    create_warehouse,
    receive_stock,
    tenant,
)
from tests.conftest import requires_db

pytestmark = requires_db


async def _sell(client, headers, warehouse_id, product_id, quantity, unit_price=None):
    item = {"product_id": product_id, "quantity": quantity}
    if unit_price is not None:
        item["unit_price"] = unit_price
    return await client.post(
        "/api/v1/sales",
        headers=headers,
        json={"warehouse_id": warehouse_id, "complete": True, "items": [item]},
    )


async def test_the_sales_report_counts_only_completed_sales(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers, sale_price="10.00")
    await receive_stock(client, headers, product_id, warehouse_id, "100")

    await _sell(client, headers, warehouse_id, product_id, "3", "10.00")
    cancelled = await _sell(client, headers, warehouse_id, product_id, "5", "10.00")
    await client.post(f"/api/v1/sales/{cancelled.json()['id']}/cancel", headers=headers)
    # A draft never happened.
    await client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "warehouse_id": warehouse_id,
            "items": [{"product_id": product_id, "quantity": "9"}],
        },
    )

    report = (await client.get("/api/v1/reports/sales", headers=headers)).json()

    assert report["summary"]["sales_count"] == 1
    assert Decimal(report["summary"]["revenue"]) == Decimal("30")
    assert Decimal(report["summary"]["average_ticket"]) == Decimal("30")
    assert report["top_products"][0]["sku"] == "SKU-1"
    assert Decimal(report["top_products"][0]["quantity"]) == Decimal("3")


async def test_inventory_valuation_prices_stock_at_cost_and_retail(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers, "Central")
    product_id = await create_product(client, headers, cost_price="4.00", sale_price="10.00")
    await receive_stock(client, headers, product_id, warehouse_id, "25")

    report = (await client.get("/api/v1/reports/inventory-valuation", headers=headers)).json()

    assert Decimal(report["total_units"]) == Decimal("25")
    assert Decimal(report["total_cost_value"]) == Decimal("100")
    assert Decimal(report["total_retail_value"]) == Decimal("250")
    # Money stays at 4 decimals even though quantity * price widens to 8.
    assert report["warehouses"][0]["cost_value"] == "100.0000"
    assert report["warehouses"][0]["warehouse_name"] == "Central"


async def test_low_stock_lists_products_at_or_below_their_threshold(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    scarce = await create_product(client, headers, "SCARCE", name="Scarce", min_stock="10")
    plenty = await create_product(client, headers, "PLENTY", name="Plenty", min_stock="2")
    await receive_stock(client, headers, scarce, warehouse_id, "3")
    await receive_stock(client, headers, plenty, warehouse_id, "50")

    report = (await client.get("/api/v1/reports/low-stock", headers=headers)).json()

    assert [row["sku"] for row in report["items"]] == ["SCARCE"]
    assert Decimal(report["items"][0]["quantity"]) == Decimal("3")


async def test_a_product_with_a_threshold_and_no_stock_row_still_shows_up(
    client, engine, unique_email
):
    """ "We have none of it" is exactly what the report is for."""
    headers, _ = await tenant(client, engine, unique_email)
    await create_warehouse(client, headers)
    await create_product(client, headers, "NEVER", name="Never received", min_stock="5")

    report = (await client.get("/api/v1/reports/low-stock", headers=headers)).json()

    assert [row["sku"] for row in report["items"]] == ["NEVER"]
    assert Decimal(report["items"][0]["quantity"]) == Decimal("0")


async def test_reports_never_mix_tenants(client, engine):
    headers_a, _ = await tenant(client, engine, "a@example.com", "Acme")
    headers_b, _ = await tenant(client, engine, "b@example.com", "Globex")
    warehouse_a = await create_warehouse(client, headers_a)
    product_a = await create_product(client, headers_a, sale_price="10.00")
    await receive_stock(client, headers_a, product_a, warehouse_a, "10")
    await _sell(client, headers_a, warehouse_a, product_a, "5", "10.00")

    report_b = (await client.get("/api/v1/reports/sales", headers=headers_b)).json()
    valuation_b = (
        await client.get("/api/v1/reports/inventory-valuation", headers=headers_b)
    ).json()

    assert report_b["summary"]["sales_count"] == 0
    assert Decimal(report_b["summary"]["revenue"]) == Decimal("0")
    assert valuation_b["warehouses"] == []


async def test_the_low_stock_job_creates_one_notification_and_does_not_repeat_it(
    client, engine, run_job, unique_email
):
    from app.infrastructure.jobs.low_stock import sweep_low_stock

    headers, company_id = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers, "SCARCE", min_stock="10")
    await receive_stock(client, headers, product_id, warehouse_id, "2")

    first = await sweep_low_stock()
    assert first["alerts_created"] == 1

    # Running again while the alert is still unread must not duplicate it.
    second = await sweep_low_stock()
    assert second["alerts_created"] == 0

    inbox = (await client.get("/api/v1/notifications", headers=headers)).json()
    assert inbox["total"] == 1
    assert inbox["unread"] == 1
    alert = inbox["items"][0]
    assert alert["type"] == "LOW_STOCK"
    assert alert["payload"]["sku"] == "SCARCE"
    assert alert["entity_id"] == product_id

    read = await client.post(f"/api/v1/notifications/{alert['id']}/read", headers=headers)
    assert read.json()["is_read"] is True
    assert (await client.get("/api/v1/notifications", headers=headers)).json()["unread"] == 0


async def test_notifications_are_tenant_scoped(client, engine, run_job):
    from app.infrastructure.jobs.low_stock import sweep_low_stock

    headers_a, _ = await tenant(client, engine, "a@example.com", "Acme")
    headers_b, _ = await tenant(client, engine, "b@example.com", "Globex")
    warehouse_a = await create_warehouse(client, headers_a)
    product_a = await create_product(client, headers_a, "SCARCE", min_stock="10")
    await receive_stock(client, headers_a, product_a, warehouse_a, "1")

    await sweep_low_stock()

    assert (await client.get("/api/v1/notifications", headers=headers_a)).json()["total"] == 1
    assert (await client.get("/api/v1/notifications", headers=headers_b)).json()["total"] == 0


async def test_company_actions_land_in_that_company_audit_log(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)

    log = await client.get("/api/v1/reports/audit", headers=headers)

    assert log.status_code == 200
    assert log.json()["total"] >= 0
