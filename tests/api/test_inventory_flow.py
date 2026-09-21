"""Warehouses, adjustments, transfers and the movement ledger."""

from decimal import Decimal

from sqlalchemy import text

from tests.api.helpers import (
    create_product,
    create_warehouse,
    receive_stock,
    stock_of,
    tenant,
)
from tests.conftest import requires_db

pytestmark = requires_db


async def test_warehouse_names_are_unique_per_company(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    await create_warehouse(client, headers, "Main")

    duplicate = await client.post("/api/v1/warehouses", headers=headers, json={"name": "Main"})

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_WAREHOUSE_NAME"


async def test_the_same_warehouse_name_is_fine_in_another_company(client, engine):
    headers_a, _ = await tenant(client, engine, "a@example.com", "Acme")
    headers_b, _ = await tenant(client, engine, "b@example.com", "Globex")

    await create_warehouse(client, headers_a, "Main")
    await create_warehouse(client, headers_b, "Main")


async def test_adjustment_moves_stock_and_leaves_a_trail(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)

    response = await client.post(
        "/api/v1/inventory/adjustments",
        headers=headers,
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity_delta": "25",
            "notes": "Opening balance",
        },
    )

    assert response.status_code == 200, response.text
    assert Decimal(response.json()["quantity"]) == Decimal("25")

    movements = await client.get(
        "/api/v1/inventory/movements", headers=headers, params={"product_id": product_id}
    )
    body = movements.json()
    assert body["total"] == 1
    assert body["items"][0]["movement_type"] == "ADJUSTMENT"
    assert body["items"][0]["notes"] == "Opening balance"


async def test_stock_cannot_be_driven_negative(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)

    response = await client.post(
        "/api/v1/inventory/adjustments",
        headers=headers,
        json={"product_id": product_id, "warehouse_id": warehouse_id, "quantity_delta": "-1"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("0")


async def test_transfer_moves_stock_between_warehouses(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    source = await create_warehouse(client, headers, "Main")
    destination = await create_warehouse(client, headers, "Branch")
    product_id = await create_product(client, headers)
    await receive_stock(client, headers, product_id, source, "10")

    response = await client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "product_id": product_id,
            "source_warehouse_id": source,
            "destination_warehouse_id": destination,
            "quantity": "4",
        },
    )

    assert response.status_code == 200, response.text
    assert await stock_of(client, headers, product_id, source) == Decimal("6")
    assert await stock_of(client, headers, product_id, destination) == Decimal("4")


async def test_a_transfer_that_would_overdraw_the_source_changes_nothing(
    client, engine, unique_email
):
    headers, _ = await tenant(client, engine, unique_email)
    source = await create_warehouse(client, headers, "Main")
    destination = await create_warehouse(client, headers, "Branch")
    product_id = await create_product(client, headers)
    await receive_stock(client, headers, product_id, source, "3")

    response = await client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "product_id": product_id,
            "source_warehouse_id": source,
            "destination_warehouse_id": destination,
            "quantity": "5",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    # The whole request rolled back: the destination never received anything.
    assert await stock_of(client, headers, product_id, source) == Decimal("3")
    assert await stock_of(client, headers, product_id, destination) == Decimal("0")


async def test_a_transfer_to_the_same_warehouse_is_rejected(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)

    response = await client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "product_id": product_id,
            "source_warehouse_id": warehouse_id,
            "destination_warehouse_id": warehouse_id,
            "quantity": "1",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SAME_WAREHOUSE_TRANSFER"


async def test_an_inactive_warehouse_refuses_stock(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)
    await client.delete(f"/api/v1/warehouses/{warehouse_id}", headers=headers)

    response = await client.post(
        "/api/v1/inventory/adjustments",
        headers=headers,
        json={"product_id": product_id, "warehouse_id": warehouse_id, "quantity_delta": "5"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INACTIVE_WAREHOUSE"


async def test_cached_stock_always_equals_the_sum_of_its_movements(client, engine, unique_email):
    """The invariant that makes the ledger trustworthy."""
    headers, company_id = await tenant(client, engine, unique_email)
    source = await create_warehouse(client, headers, "Main")
    destination = await create_warehouse(client, headers, "Branch")
    product_id = await create_product(client, headers)

    await receive_stock(client, headers, product_id, source, "20")
    await client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "product_id": product_id,
            "source_warehouse_id": source,
            "destination_warehouse_id": destination,
            "quantity": "7",
        },
    )
    await client.post(
        "/api/v1/inventory/adjustments",
        headers=headers,
        json={"product_id": product_id, "warehouse_id": source, "quantity_delta": "-2"},
    )

    async with engine.begin() as conn:
        # Without a tenant context RLS hides every row and the query would
        # pass vacuously, so enter the company first.
        await conn.execute(
            text("SELECT set_config('app.current_company_id', :company_id, true)"),
            {"company_id": company_id},
        )
        rows = (await conn.execute(text("SELECT count(*) FROM product_stock"))).scalar_one()
        assert rows == 2, "expected one stock row per warehouse"

        mismatches = (
            await conn.execute(
                text(
                    """
                    SELECT ps.product_id, ps.warehouse_id, ps.quantity,
                           COALESCE(SUM(sm.quantity), 0) AS ledger
                    FROM product_stock ps
                    LEFT JOIN stock_movements sm
                      ON sm.product_id = ps.product_id
                     AND sm.warehouse_id = ps.warehouse_id
                     AND sm.company_id = ps.company_id
                    GROUP BY ps.product_id, ps.warehouse_id, ps.quantity
                    HAVING ps.quantity <> COALESCE(SUM(sm.quantity), 0)
                    """
                )
            )
        ).all()

    assert mismatches == []
    assert await stock_of(client, headers, product_id, source) == Decimal("11")
    assert await stock_of(client, headers, product_id, destination) == Decimal("7")
