"""Sales and purchases: totals, the state machine, and their stock effects."""

import asyncio
from decimal import Decimal

from tests.api.helpers import (
    create_product,
    create_warehouse,
    receive_stock,
    stock_of,
    tenant,
)
from tests.conftest import requires_db

pytestmark = requires_db


async def _sell(client, headers, warehouse_id, product_id, quantity="2", **extra):
    payload = {
        "warehouse_id": warehouse_id,
        "items": [{"product_id": product_id, "quantity": quantity, **extra.pop("item", {})}],
        **extra,
    }
    return await client.post("/api/v1/sales", headers=headers, json=payload)


async def test_a_completed_purchase_receives_stock(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)

    response = await client.post(
        "/api/v1/purchases",
        headers=headers,
        json={
            "warehouse_id": warehouse_id,
            "complete": True,
            "items": [
                {"product_id": product_id, "quantity": "10", "unit_cost": "5.00", "tax": "1.00"}
            ],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert Decimal(body["subtotal"]) == Decimal("50")
    assert Decimal(body["total"]) == Decimal("51")
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("10")


async def test_a_draft_purchase_does_not_touch_stock(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)

    created = await client.post(
        "/api/v1/purchases",
        headers=headers,
        json={
            "warehouse_id": warehouse_id,
            "items": [{"product_id": product_id, "quantity": "10", "unit_cost": "5.00"}],
        },
    )
    assert created.json()["status"] == "DRAFT"
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("0")

    completed = await client.post(
        f"/api/v1/purchases/{created.json()['id']}/complete", headers=headers
    )
    assert completed.status_code == 200
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("10")


async def test_completing_a_purchase_can_refresh_the_product_cost(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers, cost_price="1.00")

    created = await client.post(
        "/api/v1/purchases",
        headers=headers,
        json={
            "warehouse_id": warehouse_id,
            "items": [
                {
                    "product_id": product_id,
                    "quantity": "10",
                    "unit_cost": "5.00",
                    "discount": "5.00",
                }
            ],
        },
    )
    await client.post(
        f"/api/v1/purchases/{created.json()['id']}/complete",
        headers=headers,
        params={"update_product_costs": "true"},
    )

    product = await client.get(f"/api/v1/products/{product_id}", headers=headers)
    assert Decimal(product.json()["cost_price"]) == Decimal("4.50")


async def test_cancelling_a_received_purchase_takes_the_stock_back(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)
    purchase = await client.post(
        "/api/v1/purchases",
        headers=headers,
        json={
            "warehouse_id": warehouse_id,
            "complete": True,
            "items": [{"product_id": product_id, "quantity": "6", "unit_cost": "1.00"}],
        },
    )

    response = await client.post(
        f"/api/v1/purchases/{purchase.json()['id']}/cancel", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("0")


async def test_a_completed_sale_takes_stock_out(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers, sale_price="20.00")
    await receive_stock(client, headers, product_id, warehouse_id, "10")

    response = await _sell(client, headers, warehouse_id, product_id, "3", complete=True)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "COMPLETED"
    # unit_price was omitted, so the product's sale_price applies.
    assert Decimal(body["items"][0]["unit_price"]) == Decimal("20")
    assert Decimal(body["total"]) == Decimal("60")
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("7")


async def test_a_sale_beyond_available_stock_is_refused_whole(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)
    await receive_stock(client, headers, product_id, warehouse_id, "2")

    response = await _sell(client, headers, warehouse_id, product_id, "5", complete=True)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("2")

    # The rollback took the sale with it: nothing was recorded.
    listing = await client.get("/api/v1/sales", headers=headers)
    assert listing.json()["total"] == 0


async def test_a_draft_sale_holds_no_stock_until_completed(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)
    await receive_stock(client, headers, product_id, warehouse_id, "5")

    draft = await _sell(client, headers, warehouse_id, product_id, "2")
    assert draft.json()["status"] == "DRAFT"
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("5")

    completed = await client.post(f"/api/v1/sales/{draft.json()['id']}/complete", headers=headers)
    assert completed.status_code == 200
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("3")


async def test_cancelling_a_completed_sale_restores_stock(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)
    await receive_stock(client, headers, product_id, warehouse_id, "5")
    sale = await _sell(client, headers, warehouse_id, product_id, "2", complete=True)

    response = await client.post(f"/api/v1/sales/{sale.json()['id']}/cancel", headers=headers)

    assert response.json()["status"] == "CANCELLED"
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("5")


async def test_refunding_a_sale_restores_stock_and_is_final(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)
    await receive_stock(client, headers, product_id, warehouse_id, "5")
    sale_id = (await _sell(client, headers, warehouse_id, product_id, "2", complete=True)).json()[
        "id"
    ]

    refunded = await client.post(f"/api/v1/sales/{sale_id}/refund", headers=headers)
    assert refunded.json()["status"] == "REFUNDED"
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("5")

    again = await client.post(f"/api/v1/sales/{sale_id}/refund", headers=headers)
    assert again.status_code == 422
    assert again.json()["error"]["code"] == "INVALID_SALE_TRANSITION"


async def test_a_sale_cannot_reference_another_tenants_product(client, engine):
    headers_a, _ = await tenant(client, engine, "a@example.com", "Acme")
    headers_b, _ = await tenant(client, engine, "b@example.com", "Globex")
    product_a = await create_product(client, headers_a)
    warehouse_b = await create_warehouse(client, headers_b)

    response = await _sell(client, headers_b, warehouse_b, product_a, "1")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


async def test_sales_are_invisible_across_tenants(client, engine):
    headers_a, _ = await tenant(client, engine, "a@example.com", "Acme")
    headers_b, _ = await tenant(client, engine, "b@example.com", "Globex")
    warehouse_a = await create_warehouse(client, headers_a)
    product_a = await create_product(client, headers_a)
    await receive_stock(client, headers_a, product_a, warehouse_a, "5")
    sale_id = (await _sell(client, headers_a, warehouse_a, product_a, "1", complete=True)).json()[
        "id"
    ]

    assert (await client.get(f"/api/v1/sales/{sale_id}", headers=headers_b)).status_code == 404
    assert (await client.get("/api/v1/sales", headers=headers_b)).json()["total"] == 0


async def test_a_sale_to_an_inactive_customer_is_refused(client, engine, unique_email):
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)
    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Wile E."})
    customer_id = customer.json()["id"]
    await client.delete(f"/api/v1/customers/{customer_id}", headers=headers)

    response = await _sell(client, headers, warehouse_id, product_id, "1", customer_id=customer_id)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INACTIVE_CUSTOMER"


async def test_two_concurrent_sales_cannot_spend_the_same_unit(client, engine, unique_email):
    """The row lock from BACKEND.md section 29, exercised for real.

    Both requests run at once against one unit of stock. SELECT ... FOR UPDATE
    serialises them, so the second one sees the quantity the first left behind
    and is refused -- rather than both reading 1 and both succeeding.
    """
    headers, _ = await tenant(client, engine, unique_email)
    warehouse_id = await create_warehouse(client, headers)
    product_id = await create_product(client, headers)
    await receive_stock(client, headers, product_id, warehouse_id, "1")

    first, second = await asyncio.gather(
        _sell(client, headers, warehouse_id, product_id, "1", complete=True),
        _sell(client, headers, warehouse_id, product_id, "1", complete=True),
    )

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 422], f"expected exactly one sale to win, got {statuses}"

    loser = first if first.status_code == 422 else second
    assert loser.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert await stock_of(client, headers, product_id, warehouse_id) == Decimal("0")
