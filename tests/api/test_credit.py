"""El fiado de punta a punta: fiar, abonar, cuadrar y revertir."""

from decimal import Decimal

from sqlalchemy import text

from tests.api.helpers import (
    add_member,
    balance_of,
    create_customer,
    create_product,
    create_warehouse,
    receive_stock,
    sell,
    tenant,
)
from tests.conftest import requires_db

pytestmark = requires_db


async def _tienda(client, engine, email, *, price="3700", stock="100"):
    """Una tienda lista para vender: bodega, producto surtido y una clienta."""
    hdrs, company_id = await tenant(client, engine, email, "Tienda El Progreso")
    warehouse_id = await create_warehouse(client, hdrs, "Principal")
    product_id = await create_product(client, hdrs, "GAS-01", name="Gaseosa", sale_price=price)
    await receive_stock(client, hdrs, product_id, warehouse_id, stock)
    customer_id = await create_customer(client, hdrs, "Doña Rosa", phone="3001112233")
    return hdrs, company_id, warehouse_id, product_id, customer_id


async def test_a_credit_sale_puts_the_money_on_the_customers_account(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)

    sale = await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )

    assert sale.status_code == 201, sale.text
    body = sale.json()
    assert body["payment_method"] == "CREDIT"
    assert Decimal(body["amount_paid"]) == Decimal("0")
    assert Decimal(body["outstanding"]) == Decimal("7400")

    assert await balance_of(client, hdrs, customer) == Decimal("7400.0000")


async def test_a_cash_sale_leaves_no_debt(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)

    sale = await sell(client, hdrs, warehouse, product, quantity="2", customer_id=customer)

    assert Decimal(sale.json()["outstanding"]) == Decimal("0")
    assert await balance_of(client, hdrs, customer) == Decimal("0")


async def test_a_partial_payment_leaves_only_the_rest_on_the_account(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)

    sale = await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CASH",
        amount_paid="5000",
    )

    assert Decimal(sale.json()["outstanding"]) == Decimal("2400")
    assert await balance_of(client, hdrs, customer) == Decimal("2400.0000")


async def test_you_cannot_lend_to_nobody(client, engine, unique_email):
    hdrs, _, warehouse, product, _ = await _tienda(client, engine, unique_email)

    sale = await sell(client, hdrs, warehouse, product, payment_method="CREDIT")

    assert sale.status_code == 422
    assert sale.json()["error"]["code"] == "CREDIT_SALE_NEEDS_CUSTOMER"


async def test_paying_more_than_the_sale_is_refused(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)

    sale = await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="1",
        customer_id=customer,
        amount_paid="99999",
    )

    assert sale.status_code == 422
    assert sale.json()["error"]["code"] == "OVERPAID_SALE"


async def test_a_payment_brings_the_balance_down(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)
    await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="3",
        customer_id=customer,
        payment_method="CREDIT",
    )

    response = await client.post(
        f"/api/v1/credit/accounts/{customer}/payments",
        headers=hdrs,
        json={"amount": "6000", "method": "CASH", "notes": "Abono del viernes"},
    )

    assert response.status_code == 200, response.text
    account = response.json()
    assert Decimal(account["balance"]) == Decimal("5100.0000")  # 11100 - 6000
    assert account["customer_name"] == "Doña Rosa"

    # El movimiento queda en la historia, que es de lo que se trata.
    tipos = [entry["entry_type"] for entry in account["entries"]]
    assert tipos == ["PAYMENT", "SALE"], "lo más reciente primero"
    assert account["entries"][0]["notes"] == "Abono del viernes"


async def test_paying_more_than_owed_is_refused(client, engine, unique_email):
    """Dejar el saldo en negativo lo convertiría en un anticipo, que es otro
    producto."""
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)
    await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="1",
        customer_id=customer,
        payment_method="CREDIT",
    )

    response = await client.post(
        f"/api/v1/credit/accounts/{customer}/payments", headers=hdrs, json={"amount": "50000"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PAYMENT_EXCEEDS_BALANCE"
    assert response.json()["error"]["details"]["balance"] == "3700.0000"


async def test_paying_the_whole_balance_closes_the_account(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)
    await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )

    await client.post(
        f"/api/v1/credit/accounts/{customer}/payments", headers=hdrs, json={"amount": "7400"}
    )

    assert await balance_of(client, hdrs, customer) == Decimal("0.0000")


async def test_cancelling_a_credit_sale_wipes_the_debt(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)
    sale = await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )
    assert await balance_of(client, hdrs, customer) == Decimal("7400.0000")

    cancelled = await client.post(f"/api/v1/sales/{sale.json()['id']}/cancel", headers=hdrs)

    assert cancelled.json()["status"] == "CANCELLED"
    assert await balance_of(client, hdrs, customer) == Decimal("0.0000")

    account = (await client.get(f"/api/v1/credit/accounts/{customer}", headers=hdrs)).json()
    assert account["entries"][0]["entry_type"] == "SALE_REVERSED"
    assert account["entries"][0]["notes"] == "Venta cancelada"


async def test_refunding_a_credit_sale_wipes_the_debt(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)
    sale = await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )

    refunded = await client.post(f"/api/v1/sales/{sale.json()['id']}/refund", headers=hdrs)

    assert refunded.json()["status"] == "REFUNDED"
    assert await balance_of(client, hdrs, customer) == Decimal("0.0000")


async def test_a_draft_credit_sale_does_not_charge_the_account(client, engine, unique_email):
    """Un borrador no ocurrió: no descuenta stock ni genera deuda."""
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)

    draft = await client.post(
        "/api/v1/sales",
        headers=hdrs,
        json={
            "warehouse_id": warehouse,
            "customer_id": customer,
            "payment_method": "CREDIT",
            "items": [{"product_id": product, "quantity": "2"}],
        },
    )
    assert draft.json()["status"] == "DRAFT"
    assert await balance_of(client, hdrs, customer) == Decimal("0")

    await client.post(f"/api/v1/sales/{draft.json()['id']}/complete", headers=hdrs)
    assert await balance_of(client, hdrs, customer) == Decimal("7400.0000")


async def test_the_credit_limit_stops_the_sale(client, engine, unique_email):
    hdrs, _, warehouse, product, _ = await _tienda(client, engine, unique_email)
    customer = await create_customer(client, hdrs, "Don Pedro", credit_limit="10000")

    await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )  # 7400, cabe

    excede = await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="1",
        customer_id=customer,
        payment_method="CREDIT",
    )  # 7400 + 3700 = 11100 > 10000

    assert excede.status_code == 422
    assert excede.json()["error"]["code"] == "CREDIT_LIMIT_EXCEEDED"
    detalles = excede.json()["error"]["details"]
    assert detalles["balance"] == "7400.0000"
    assert detalles["credit_limit"] == "10000.0000"

    # Y el saldo quedó donde estaba: la venta se revirtió entera.
    assert await balance_of(client, hdrs, customer) == Decimal("7400.0000")


async def test_without_a_limit_there_is_no_ceiling(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)

    for _ in range(3):
        sale = await sell(
            client,
            hdrs,
            warehouse,
            product,
            quantity="5",
            customer_id=customer,
            payment_method="CREDIT",
        )
        assert sale.status_code == 201

    assert await balance_of(client, hdrs, customer) == Decimal("55500.0000")


async def test_an_adjustment_forgives_debt_and_says_why(client, engine, unique_email):
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)
    await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )

    response = await client.post(
        f"/api/v1/credit/accounts/{customer}/adjustments",
        headers=hdrs,
        json={"amount": "-400", "notes": "Le perdoné el redondeo"},
    )

    assert response.status_code == 200, response.text
    assert Decimal(response.json()["balance"]) == Decimal("7000.0000")
    assert response.json()["entries"][0]["entry_type"] == "ADJUSTMENT"


async def test_an_adjustment_without_a_reason_is_refused(client, engine, unique_email):
    """Un ajuste sin explicación es lo que vuelve turbias las cuentas."""
    hdrs, _, _, _, customer = await _tienda(client, engine, unique_email)

    response = await client.post(
        f"/api/v1/credit/accounts/{customer}/adjustments",
        headers=hdrs,
        json={"amount": "-400"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_cuentas_claras_lists_who_owes_most_first(client, engine, unique_email):
    hdrs, _, warehouse, product, rosa = await _tienda(client, engine, unique_email)
    pedro = await create_customer(client, hdrs, "Don Pedro")
    al_dia = await create_customer(client, hdrs, "Vecina al día")

    await sell(
        client, hdrs, warehouse, product, quantity="2", customer_id=rosa, payment_method="CREDIT"
    )  # 7400
    await sell(
        client, hdrs, warehouse, product, quantity="5", customer_id=pedro, payment_method="CREDIT"
    )  # 18500
    await sell(client, hdrs, warehouse, product, quantity="1", customer_id=al_dia)  # contado

    accounts = (await client.get("/api/v1/credit/accounts", headers=hdrs)).json()

    assert [a["customer_name"] for a in accounts["items"]] == ["Don Pedro", "Doña Rosa"]
    assert Decimal(accounts["items"][0]["balance"]) == Decimal("18500.0000")
    assert accounts["items"][0]["phone"] is None
    assert accounts["total"] == 2, "quien está al día no aparece"

    con_todos = await client.get(
        "/api/v1/credit/accounts", headers=hdrs, params={"only_with_balance": "false"}
    )
    assert con_todos.json()["total"] == 3

    summary = (await client.get("/api/v1/credit/summary", headers=hdrs)).json()
    assert summary["customers_with_debt"] == 2
    assert Decimal(summary["total_receivable"]) == Decimal("25900.0000")


async def test_searching_an_account_by_name_or_phone(client, engine, unique_email):
    hdrs, _, warehouse, product, rosa = await _tienda(client, engine, unique_email)
    await sell(client, hdrs, warehouse, product, customer_id=rosa, payment_method="CREDIT")

    por_nombre = await client.get(
        "/api/v1/credit/accounts", headers=hdrs, params={"search": "rosa"}
    )
    por_telefono = await client.get(
        "/api/v1/credit/accounts", headers=hdrs, params={"search": "300111"}
    )

    assert por_nombre.json()["total"] == 1
    assert por_telefono.json()["total"] == 1


async def test_a_seller_can_lend_and_take_payments(client, engine, unique_email):
    """Fiar es el mostrador: el vendedor tiene que poder."""
    owner, company_id, warehouse, product, customer = await _tienda(client, engine, unique_email)
    seller = await add_member(client, owner, company_id, "vendedor@example.com", "SELLER")

    sale = await sell(
        client,
        seller,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )
    assert sale.status_code == 201

    payment = await client.post(
        f"/api/v1/credit/accounts/{customer}/payments", headers=seller, json={"amount": "1000"}
    )
    assert payment.status_code == 200
    assert Decimal(payment.json()["balance"]) == Decimal("6400.0000")


async def test_the_balance_always_equals_its_movements(client, engine, unique_email):
    """El invariante que vuelve confiable el libro, igual que con el stock."""
    hdrs, company_id, warehouse, product, customer = await _tienda(client, engine, unique_email)
    await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="3",
        customer_id=customer,
        payment_method="CREDIT",
    )
    await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CASH",
        amount_paid="1000",
    )
    await client.post(
        f"/api/v1/credit/accounts/{customer}/payments", headers=hdrs, json={"amount": "5000"}
    )
    await client.post(
        f"/api/v1/credit/accounts/{customer}/adjustments",
        headers=hdrs,
        json={"amount": "-500", "notes": "Redondeo"},
    )

    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_company_id', :c, true)"),
            {"c": company_id},
        )
        filas = (await conn.execute(text("SELECT count(*) FROM customer_balances"))).scalar_one()
        descuadres = (
            await conn.execute(
                text(
                    """
                    SELECT b.customer_id, b.balance, COALESCE(SUM(e.amount), 0) AS libro
                    FROM customer_balances b
                    LEFT JOIN customer_account_entries e
                      ON e.customer_id = b.customer_id AND e.company_id = b.company_id
                    GROUP BY b.customer_id, b.balance
                    HAVING b.balance <> COALESCE(SUM(e.amount), 0)
                    """
                )
            )
        ).all()

    assert filas == 1, "la cuenta existe de verdad"
    assert descuadres == []
    # 11100 + 6400 - 5000 - 500
    assert await balance_of(client, hdrs, customer) == Decimal("12000.0000")


async def test_accounts_are_invisible_across_tenants(client, engine):
    hdrs_a, _, warehouse_a, product_a, rosa = await _tienda(client, engine, "a@example.com")
    hdrs_b, _ = await tenant(client, engine, "b@example.com", "Otra Tienda")
    await sell(client, hdrs_a, warehouse_a, product_a, customer_id=rosa, payment_method="CREDIT")

    assert (await client.get(f"/api/v1/credit/accounts/{rosa}", headers=hdrs_b)).status_code == 404
    assert (await client.get("/api/v1/credit/accounts", headers=hdrs_b)).json()["total"] == 0
    assert (await client.get("/api/v1/credit/summary", headers=hdrs_b)).json()[
        "total_receivable"
    ] == "0"


async def test_refunding_a_partly_paid_credit_sale_leaves_money_in_favour(
    client, engine, unique_email
):
    """El caso que el modelo tenía que decidir.

    Doña Rosa fía 7400, abona 5000 y después devuelve la mercancía. Pagó por
    algo que ya no tiene, así que la tienda le queda debiendo. El sistema no
    puede saber si el tendero le entregó la plata o se la dejó para la próxima:
    lo registra y lo muestra, y el tendero lo salda cuando corresponda.
    """
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)
    sale = await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )
    await client.post(
        f"/api/v1/credit/accounts/{customer}/payments", headers=hdrs, json={"amount": "5000"}
    )

    await client.post(f"/api/v1/sales/{sale.json()['id']}/refund", headers=hdrs)

    account = (await client.get(f"/api/v1/credit/accounts/{customer}", headers=hdrs)).json()
    assert Decimal(account["balance"]) == Decimal("-5000.0000")
    assert Decimal(account["owes"]) == Decimal("0")
    assert Decimal(account["in_favor"]) == Decimal("5000.0000")

    # Sigue siendo una cuenta abierta, así que aparece en la lista -- esconder
    # una deuda de la tienda sería justo lo contrario de "cuentas claras".
    accounts = (await client.get("/api/v1/credit/accounts", headers=hdrs)).json()
    assert [a["customer_name"] for a in accounts["items"]] == ["Doña Rosa"]
    assert Decimal(accounts["items"][0]["balance"]) == Decimal("-5000.0000")

    # Pero no cuenta como algo por cobrar.
    summary = (await client.get("/api/v1/credit/summary", headers=hdrs)).json()
    assert summary["customers_with_debt"] == 0
    assert Decimal(summary["total_receivable"]) == Decimal("0")


async def test_an_account_separates_what_is_owed_from_what_is_in_favour(
    client, engine, unique_email
):
    """La pantalla no debería tener que razonar sobre signos."""
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)
    await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )

    account = (await client.get(f"/api/v1/credit/accounts/{customer}", headers=hdrs)).json()

    assert Decimal(account["owes"]) == Decimal("7400.0000")
    assert Decimal(account["in_favor"]) == Decimal("0")


async def test_a_customer_with_money_in_favour_can_be_settled_with_an_adjustment(
    client, engine, unique_email
):
    """Cuando el tendero sí le entregó la plata, cierra la cuenta con un ajuste
    que deja dicho por qué."""
    hdrs, _, warehouse, product, customer = await _tienda(client, engine, unique_email)
    sale = await sell(
        client,
        hdrs,
        warehouse,
        product,
        quantity="2",
        customer_id=customer,
        payment_method="CREDIT",
    )
    await client.post(
        f"/api/v1/credit/accounts/{customer}/payments", headers=hdrs, json={"amount": "5000"}
    )
    await client.post(f"/api/v1/sales/{sale.json()['id']}/refund", headers=hdrs)

    response = await client.post(
        f"/api/v1/credit/accounts/{customer}/adjustments",
        headers=hdrs,
        json={"amount": "5000", "notes": "Le devolví los 5 mil en efectivo"},
    )

    assert response.status_code == 200, response.text
    assert Decimal(response.json()["balance"]) == Decimal("0.0000")
    assert Decimal(response.json()["in_favor"]) == Decimal("0")
