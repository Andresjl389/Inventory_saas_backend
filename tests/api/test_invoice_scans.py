"""Escanear la factura del proveedor, de punta a punta.

Lo que se prueba es la promesa del módulo: la foto propone, una persona decide
y solo entonces se mueve el inventario. Cada prueba va contra una forma
concreta de romper esa promesa.
"""

from decimal import Decimal

from tests.api.helpers import (
    create_product,
    create_warehouse,
    line_by_description,
    scan_invoice,
    stock_of,
    tenant,
)
from tests.conftest import requires_db

pytestmark = requires_db

FACTURA = """\
Proveedor: Distribuidora El Sol
NIT: 900.123.456-7
Factura: F-00123
Fecha: 15/10/2026
Total: 41.000
---
2 | ARROZ DIANA X500GR | 2.500
3 | ACEITE PREMIER 1L | 12.000
1 | Flete | 0
"""


async def _tienda(client, engine, email):
    """Una tienda con bodega y un solo producto en el catálogo: el arroz."""
    hdrs, company_id = await tenant(client, engine, email, "Tienda El Progreso")
    warehouse_id = await create_warehouse(client, hdrs, "Principal")
    arroz = await create_product(
        client, hdrs, "ARR-500", name="Arroz Diana 500 g", cost_price="2400"
    )
    return hdrs, company_id, warehouse_id, arroz


async def test_the_scan_proposes_what_it_recognises_and_leaves_the_rest_pending(
    client, engine, unique_email
):
    hdrs, _, warehouse, arroz = await _tienda(client, engine, unique_email)

    response = await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)

    assert response.status_code == 201, response.text
    scan = response.json()
    assert scan["status"] == "EXTRACTED"
    assert scan["invoice_number"] == "F-00123"
    assert Decimal(scan["declared_total"]) == Decimal("41000")

    # El arroz está en el catálogo con otro nombre: se enlaza solo.
    assert line_by_description(scan, "arroz")["action"] == "LINK"
    assert line_by_description(scan, "arroz")["product_id"] == arroz
    # El aceite y el flete no: nadie los decide por el usuario.
    assert line_by_description(scan, "aceite")["action"] == "PENDING"
    assert line_by_description(scan, "flete")["action"] == "PENDING"
    assert scan["pending_count"] == 2


async def test_nothing_is_written_until_somebody_confirms(client, engine, unique_email):
    hdrs, _, warehouse, arroz = await _tienda(client, engine, unique_email)

    await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)

    assert await stock_of(client, hdrs, arroz, warehouse) == Decimal("0")
    purchases = await client.get("/api/v1/purchases", headers=hdrs)
    assert purchases.json()["total"] == 0


async def test_confirming_with_undecided_lines_is_refused(client, engine, unique_email):
    hdrs, _, warehouse, _ = await _tienda(client, engine, unique_email)
    scan = (await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)).json()

    response = await client.post(
        f"/api/v1/invoices/scans/{scan['id']}/confirm", headers=hdrs, json={}
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "UNDECIDED_LINES"


async def test_confirming_without_a_warehouse_is_refused(client, engine, unique_email):
    """Quien toma la foto en el mostrador no siempre sabe a qué bodega entra."""
    hdrs, _, _, _ = await _tienda(client, engine, unique_email)
    scan = (await scan_invoice(client, hdrs, "2 | ARROZ DIANA X500GR | 2.500\n")).json()

    response = await client.post(
        f"/api/v1/invoices/scans/{scan['id']}/confirm", headers=hdrs, json={}
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "WAREHOUSE_REQUIRED"


async def test_a_reviewed_scan_becomes_a_purchase_and_moves_the_stock(client, engine, unique_email):
    hdrs, _, warehouse, arroz = await _tienda(client, engine, unique_email)
    scan = (await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)).json()

    review = await client.patch(
        f"/api/v1/invoices/scans/{scan['id']}",
        headers=hdrs,
        json={
            "lines": [
                {
                    "line_id": line_by_description(scan, "aceite")["id"],
                    "action": "CREATE",
                    "new_product": {"sale_price": "15000"},
                },
                {"line_id": line_by_description(scan, "flete")["id"], "action": "SKIP"},
            ]
        },
    )
    assert review.status_code == 200, review.text
    reviewed = review.json()
    # Sin renglones sin decidir, el escaneo queda listo -- lo dice el trabajo
    # que falta, no un botón.
    assert reviewed["status"] == "REVIEWED"
    assert reviewed["pending_count"] == 0
    # El flete descartado explica la diferencia contra el total impreso.
    assert Decimal(reviewed["lines_total"]) == Decimal("41000")

    confirm = await client.post(
        f"/api/v1/invoices/scans/{scan['id']}/confirm",
        headers=hdrs,
        json={"complete": True, "update_product_costs": True},
    )
    assert confirm.status_code == 200, confirm.text
    result = confirm.json()

    assert result["scan"]["status"] == "CONFIRMED"
    assert result["purchase"]["status"] == "COMPLETED"
    assert Decimal(result["purchase"]["total"]) == Decimal("41000")
    # Dos renglones de mercancía; el flete no entró a la compra.
    assert len(result["purchase"]["items"]) == 2
    assert len(result["created_product_ids"]) == 1

    assert await stock_of(client, hdrs, arroz, warehouse) == Decimal("2")
    nuevo = result["created_product_ids"][0]
    assert await stock_of(client, hdrs, nuevo, warehouse) == Decimal("3")

    created = (await client.get(f"/api/v1/products/{nuevo}", headers=hdrs)).json()
    assert created["name"] == "ACEITE PREMIER 1L"
    # El costo lo dice la factura; el precio de venta lo puso la persona.
    assert Decimal(created["cost_price"]) == Decimal("12000")
    assert Decimal(created["sale_price"]) == Decimal("15000")
    # El producto quedó con rastro de dónde salió.
    line = line_by_description(result["scan"], "aceite")
    assert line["action"] == "LINK"
    assert line["new_product"]["created_product_id"] == nuevo


async def test_a_confirmed_scan_cannot_be_confirmed_again(client, engine, unique_email):
    """La protección contra el doble toque: confirmar dos veces duplicaría el
    inventario."""
    hdrs, _, warehouse, _ = await _tienda(client, engine, unique_email)
    scan = (
        await scan_invoice(client, hdrs, "2 | ARROZ DIANA X500GR | 2.500\n", warehouse_id=warehouse)
    ).json()

    first = await client.post(f"/api/v1/invoices/scans/{scan['id']}/confirm", headers=hdrs, json={})
    assert first.status_code == 200, first.text

    again = await client.post(f"/api/v1/invoices/scans/{scan['id']}/confirm", headers=hdrs, json={})
    assert again.status_code == 422
    assert again.json()["error"]["code"] == "SCAN_NOT_OPEN"


async def test_rematching_picks_up_a_product_created_after_the_scan(client, engine, unique_email):
    """El caso real: se escanea, se cae en cuenta de que faltaba un producto,
    se crea, y el renglón que estaba en el aire se acomoda."""
    hdrs, _, warehouse, _ = await _tienda(client, engine, unique_email)
    scan = (await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)).json()
    assert line_by_description(scan, "aceite")["action"] == "PENDING"

    aceite = await create_product(client, hdrs, "ACE-1L", name="Aceite Premier 1 L")

    response = await client.post(f"/api/v1/invoices/scans/{scan['id']}/rematch", headers=hdrs)

    assert response.status_code == 200, response.text
    assert line_by_description(response.json(), "aceite")["product_id"] == aceite


async def test_rematching_never_undoes_a_decision(client, engine, unique_email):
    hdrs, _, warehouse, _ = await _tienda(client, engine, unique_email)
    scan = (await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)).json()
    flete = line_by_description(scan, "flete")["id"]
    await client.patch(
        f"/api/v1/invoices/scans/{scan['id']}",
        headers=hdrs,
        json={"lines": [{"line_id": flete, "action": "SKIP"}]},
    )

    response = await client.post(f"/api/v1/invoices/scans/{scan['id']}/rematch", headers=hdrs)

    assert line_by_description(response.json(), "flete")["action"] == "SKIP"


async def test_a_document_with_no_lines_is_refused(client, engine, unique_email):
    hdrs, _, warehouse, _ = await _tienda(client, engine, unique_email)

    response = await scan_invoice(client, hdrs, "Proveedor: Nadie\n", warehouse_id=warehouse)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "EMPTY_INVOICE"


async def test_a_cancelled_scan_accepts_no_more_changes(client, engine, unique_email):
    hdrs, _, warehouse, _ = await _tienda(client, engine, unique_email)
    scan = (await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)).json()

    cancelled = await client.post(f"/api/v1/invoices/scans/{scan['id']}/cancel", headers=hdrs)
    assert cancelled.json()["status"] == "CANCELLED"

    review = await client.patch(
        f"/api/v1/invoices/scans/{scan['id']}", headers=hdrs, json={"lines": []}
    )
    assert review.status_code == 422
    assert review.json()["error"]["code"] == "SCAN_NOT_OPEN"


async def test_another_companys_scan_simply_does_not_exist(client, engine, unique_email):
    hdrs, _, warehouse, _ = await _tienda(client, engine, unique_email)
    scan = (await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)).json()

    other, _ = await tenant(client, engine, f"otra-{unique_email}", "Tienda La Esquina")

    response = await client.get(f"/api/v1/invoices/scans/{scan['id']}", headers=other)

    assert response.status_code == 404


async def test_the_scan_links_the_supplier_the_invoice_names(client, engine, unique_email):
    """El NIT impreso contra el NIT guardado: coincidencia exacta o nada."""
    hdrs, _, warehouse, _ = await _tienda(client, engine, unique_email)
    supplier = await client.post(
        "/api/v1/suppliers",
        headers=hdrs,
        json={
            "name": "Distribuidora El Sol",
            "document_type": "NIT",
            "document_number": "900123456-7",
        },
    )
    assert supplier.status_code == 201, supplier.text

    scan = (await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)).json()

    assert scan["supplier_id"] == supplier.json()["id"]


async def test_a_confirmed_scan_becomes_labelled_training_data(
    client, engine, run_job, unique_email, tmp_path
):
    """El activo del modelo propio: cada factura revisada queda como un par
    (imagen, JSON correcto), que es el formato de entrenamiento y el de la
    evaluación. Nadie etiquetó nada a propósito."""
    from app.infrastructure.invoices.corpus import export_corpus

    hdrs, _, warehouse, arroz = await _tienda(client, engine, unique_email)
    scan = (await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)).json()
    # El aceite se leyó como "ACEITE PREMIER 1L" y la persona lo corrige.
    await client.patch(
        f"/api/v1/invoices/scans/{scan['id']}",
        headers=hdrs,
        json={
            "lines": [
                {
                    "line_id": line_by_description(scan, "aceite")["id"],
                    "action": "CREATE",
                    "unit_cost": "12500",
                },
                {"line_id": line_by_description(scan, "flete")["id"], "action": "SKIP"},
            ]
        },
    )
    await client.post(f"/api/v1/invoices/scans/{scan['id']}/confirm", headers=hdrs, json={})

    report = await export_corpus(tmp_path)

    assert report.written == 1
    documents = sorted(path.name for path in tmp_path.iterdir())
    assert documents == [f"{scan['id']}.json", f"{scan['id']}.txt"]

    import json

    record = json.loads((tmp_path / f"{scan['id']}.json").read_text())
    # La verdad es lo que dejó la persona, no lo que leyó el modelo.
    aceite = next(line for line in record["truth"]["lines"] if "ACEITE" in line["description"])
    assert aceite["unit_cost"] == "12500.0000"
    # Y la lectura cruda queda al lado, que es lo que permite medir el modelo.
    read = next(line for line in record["read"]["lines"] if "ACEITE" in line["description"])
    assert read["unit_cost"] == "12000"
    assert record["source"] == "text"
    # El renglón corregido cuenta como error del modelo, y se ve en el reporte.
    assert report.as_dict()["line_accuracy"] == 0.6667


async def test_an_oversized_photo_is_refused_before_it_is_read(client, engine, unique_email):
    hdrs, _, _, _ = await _tienda(client, engine, unique_email)

    # La suite fija MAX_UPLOAD_SIZE_MB=1.
    response = await scan_invoice(client, hdrs, "1 | ARROZ | 1\n" * 120_000)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_while_the_model_is_deferred_the_endpoint_says_so_and_stores_nothing(
    client, engine, unique_email, monkeypatch
):
    """Con el modelo apagado, subir la foto y guardarla sería dejar basura: el
    error sale al resolver la dependencia, antes de que el endpoint corra."""
    from app.infrastructure.invoices.factory import get_invoice_extractor
    from app.shared.config.settings import settings

    hdrs, _, warehouse, _ = await _tienda(client, engine, unique_email)

    monkeypatch.setattr(settings, "invoice_extractor", "disabled")
    get_invoice_extractor.cache_clear()
    try:
        response = await scan_invoice(client, hdrs, FACTURA, warehouse_id=warehouse)
    finally:
        get_invoice_extractor.cache_clear()

    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "INVOICE_SCANNING_DISABLED"

    files = await client.get("/api/v1/files", headers=hdrs, params={"owner_type": "INVOICE"})
    assert files.json()["total"] == 0
    assert (await client.get("/api/v1/invoices/scans", headers=hdrs)).json()["total"] == 0


async def test_health_tells_the_frontend_whether_scanning_is_on(client):
    """Para que la pantalla oculte el botón en vez de descubrirlo fallando."""
    features = (await client.get("/health")).json()["features"]

    assert features["invoice_scanning"] is True
