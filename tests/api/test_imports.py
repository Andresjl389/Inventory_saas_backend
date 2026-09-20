"""The import pipeline, end to end, on a file that looks like a real one."""

from decimal import Decimal

from tests.api.helpers import (
    XLSX_MEDIA_TYPE,
    create_warehouse,
    start_import,
    tenant,
    workbook_bytes,
)
from tests.conftest import requires_db

pytestmark = requires_db

# Headers nobody would map by hand the same way twice, values in the shapes a
# Latin-American export produces.
MESSY_PRODUCTS = [
    ["Inventario general", None, None, None, None],
    [None, None, None, None, None],
    ["Referencia", "Articulo", "PVP", "Familia", "Centro de costo interno"],
    ["mar-01", "Martillo de carpintero", "$ 15.000", "Herramientas", "CC-900"],
    [None, None, None, None, None],
    ["DES-02", "Destornillador", "8.500,50", "Herramientas", "CC-900"],
    ["TOR-03", "Torníquete", "1.234,56", "Ferretería", "CC-901"],
]


async def test_the_template_is_a_real_workbook_that_maps_to_itself(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)

    response = await client.get("/api/v1/imports/templates/PRODUCTS", headers=hdrs)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(XLSX_MEDIA_TYPE)
    assert "plantilla_products.xlsx" in response.headers["content-disposition"]

    # Uploading the template back maps every column without a single choice.
    analysed = await start_import(client, hdrs, entity="PRODUCTS", payload=response.content)
    assert analysed.status_code == 201
    body = analysed.json()
    assert body["missing_required"] == []
    assert all(column["suggested_target"] for column in body["columns"])


async def test_schemas_describe_every_entity_for_a_mapping_screen(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)

    schemas = (await client.get("/api/v1/imports/schemas", headers=hdrs)).json()

    by_entity = {item["entity"]: item for item in schemas}
    assert list(by_entity) == [
        "CATEGORIES",
        "WAREHOUSES",
        "PRODUCTS",
        "CUSTOMERS",
        "SUPPLIERS",
        "STOCK",
    ], "listed in the order they must be imported"
    products = by_entity["PRODUCTS"]
    assert products["key_field"] == "sku"
    assert {field["key"] for field in products["fields"]} >= {"sku", "name", "sale_price"}
    assert products["template_url"].endswith("/imports/templates/PRODUCTS")


async def test_analysis_proposes_a_mapping_and_writes_nothing(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)

    response = await start_import(
        client, hdrs, entity="PRODUCTS", payload=workbook_bytes(MESSY_PRODUCTS)
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["total_rows"] == 3, "the title, the blank row and the header are not data"

    suggested = {c["source"]: c["suggested_target"] for c in body["columns"]}
    assert suggested["Referencia"] == "sku"
    assert suggested["Articulo"] == "name"
    assert suggested["PVP"] == "sale_price"
    assert suggested["Familia"] == "category"
    assert suggested["Centro de costo interno"] is None, "a column we do not know stays unmapped"

    # A confident match is not flagged; a plausible-but-uncertain one is, so
    # the mapping screen can highlight it instead of accepting it silently.
    by_source = {c["source"]: c for c in body["columns"]}
    assert by_source["Referencia"]["needs_review"] is False
    assert by_source["PVP"]["needs_review"] is False

    # The preview shows the conversion before anything is written.
    first = {cell["field_key"]: cell for cell in body["preview"][0]["cells"]}
    assert first["sale_price"]["raw"] == "$ 15.000"
    assert first["sale_price"]["value"] == "15000"

    assert (await client.get("/api/v1/products", headers=hdrs)).json()["total"] == 0


async def test_a_dry_run_reports_what_would_happen_and_undoes_it(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    job = (
        await start_import(client, hdrs, entity="PRODUCTS", payload=workbook_bytes(MESSY_PRODUCTS))
    ).json()["job"]

    validated = await client.post(f"/api/v1/imports/{job['id']}/validate", headers=hdrs)

    assert validated.status_code == 200, validated.text
    body = validated.json()
    assert body["dry_run"] is True
    assert body["stats"]["created"] == 3
    assert body["stats"]["errors"] == 0
    assert body["job"]["status"] == "VALIDATED"

    assert (await client.get("/api/v1/products", headers=hdrs)).json()["total"] == 0, (
        "a dry run must leave the company untouched"
    )


async def test_running_the_import_creates_the_records(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    job = (
        await start_import(client, hdrs, entity="PRODUCTS", payload=workbook_bytes(MESSY_PRODUCTS))
    ).json()["job"]

    result = await client.post(f"/api/v1/imports/{job['id']}/run", headers=hdrs)

    assert result.status_code == 200, result.text
    assert result.json()["stats"] == {
        "total_rows": 3,
        "created": 3,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }
    assert result.json()["job"]["status"] == "COMPLETED"

    products = (await client.get("/api/v1/products", headers=hdrs)).json()
    assert products["total"] == 3
    by_sku = {item["sku"]: item for item in products["items"]}
    assert by_sku["MAR-01"]["name"] == "Martillo de carpintero"
    assert Decimal(by_sku["MAR-01"]["sale_price"]) == Decimal("15000")
    assert Decimal(by_sku["DES-02"]["sale_price"]) == Decimal("8500.50")

    # The categories named in the file were created along the way.
    categories = (await client.get("/api/v1/categories", headers=hdrs)).json()
    assert {item["name"] for item in categories} == {"Herramientas", "Ferretería"}


async def test_importing_the_same_file_again_updates_instead_of_failing(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    payload = workbook_bytes(MESSY_PRODUCTS)
    first = (await start_import(client, hdrs, entity="PRODUCTS", payload=payload)).json()["job"]
    await client.post(f"/api/v1/imports/{first['id']}/run", headers=hdrs)

    second = (await start_import(client, hdrs, entity="PRODUCTS", payload=payload)).json()["job"]
    result = await client.post(f"/api/v1/imports/{second['id']}/run", headers=hdrs)

    assert result.json()["stats"]["updated"] == 3
    assert result.json()["stats"]["created"] == 0
    assert (await client.get("/api/v1/products", headers=hdrs)).json()["total"] == 3


async def test_correcting_the_mapping_changes_what_gets_imported(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    analysis = (
        await start_import(client, hdrs, entity="PRODUCTS", payload=workbook_bytes(MESSY_PRODUCTS))
    ).json()
    job_id = analysis["job"]["id"]

    remapped = await client.patch(
        f"/api/v1/imports/{job_id}/mapping",
        headers=hdrs,
        json={
            "mapping": {
                "Referencia": "sku",
                "Articulo": "name",
                "PVP": "cost_price",
                "Centro de costo interno": "barcode",
            }
        },
    )

    assert remapped.status_code == 200, remapped.text
    result = (await client.post(f"/api/v1/imports/{job_id}/run", headers=hdrs)).json()

    products = (await client.get("/api/v1/products", headers=hdrs)).json()["items"]
    product = next(item for item in products if item["sku"] == "MAR-01")
    assert Decimal(product["cost_price"]) == Decimal("15000")
    assert Decimal(product["sale_price"]) == Decimal("0")
    assert product["barcode"] == "CC-900"

    # Two rows carried CC-900. Barcodes are unique per company, so the second
    # product loads without one rather than the whole import failing.
    assert result["stats"]["created"] == 3
    repeated = next(item for item in products if item["sku"] == "DES-02")
    assert repeated["barcode"] is None
    assert any("se repite en el archivo" in e["message"] for e in result["errors_preview"])


async def test_pinning_the_decimal_separator_overrides_the_guess(client, unique_email):
    """For a file where 15.000 really does mean fifteen."""
    hdrs, _ = await tenant(client, unique_email)
    analysis = (
        await start_import(
            client,
            hdrs,
            entity="PRODUCTS",
            payload=workbook_bytes(
                [["Referencia", "Articulo", "PVP"], ["A-1", "Tornillo", "15.000"]]
            ),
        )
    ).json()
    job_id = analysis["job"]["id"]

    preview = analysis["preview"][0]["cells"]
    assert {c["field_key"]: c["value"] for c in preview}["sale_price"] == "15000"

    remapped = await client.patch(
        f"/api/v1/imports/{job_id}/mapping",
        headers=hdrs,
        json={
            "mapping": {"Referencia": "sku", "Articulo": "name", "PVP": "sale_price"},
            "decimal_separator": ".",
        },
    )

    cells = {c["field_key"]: c["value"] for c in remapped.json()["preview"][0]["cells"]}
    assert cells["sale_price"] == "15.000"


async def test_bad_rows_are_reported_by_row_number_and_the_rest_still_load(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    payload = workbook_bytes(
        [
            ["Referencia", "Articulo", "PVP"],
            ["A-1", "Bueno", "1000"],
            ["", "Sin referencia", "2000"],
            ["A-3", "Precio raro", "mil pesos"],
            ["A-1", "Repetido", "1500"],
        ]
    )
    job = (await start_import(client, hdrs, entity="PRODUCTS", payload=payload)).json()["job"]

    result = (await client.post(f"/api/v1/imports/{job['id']}/run", headers=hdrs)).json()

    assert result["stats"]["created"] == 1, "A-3 fails, A-1 folds into one row"
    assert result["stats"]["errors"] == 3

    errors = (await client.get(f"/api/v1/imports/{job['id']}/errors", headers=hdrs)).json()
    by_row = {item["row_number"]: item["message"] for item in errors["items"]}
    assert "obligatorio" in by_row[3]
    assert "no es" in by_row[4].lower() or "not a valid number" in by_row[4]
    assert "Repetido en el archivo" in by_row[2]

    # The one good row is the surviving A-1, which is the later of the two.
    products = (await client.get("/api/v1/products", headers=hdrs)).json()["items"]
    assert [(p["sku"], p["name"]) for p in products] == [("A-1", "Repetido")]


async def test_a_mapping_missing_a_required_field_is_refused_before_loading(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    job = (
        await start_import(
            client,
            hdrs,
            entity="PRODUCTS",
            payload=workbook_bytes([["Articulo", "PVP"], ["Martillo", "1000"]]),
        )
    ).json()["job"]

    result = await client.post(f"/api/v1/imports/{job['id']}/run", headers=hdrs)

    assert result.status_code == 422
    assert result.json()["error"]["code"] == "MISSING_REQUIRED_COLUMNS"
    assert result.json()["error"]["details"]["missing"] == ["sku"]


async def test_an_unknown_target_field_is_refused(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    job = (
        await start_import(client, hdrs, entity="PRODUCTS", payload=workbook_bytes([["A"], ["1"]]))
    ).json()["job"]

    response = await client.patch(
        f"/api/v1/imports/{job['id']}/mapping", headers=hdrs, json={"mapping": {"A": "precio"}}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_TARGET_FIELD"


async def test_stock_import_creates_movements_so_the_ledger_still_adds_up(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    await create_warehouse(client, hdrs, "Bodega Central")
    products_job = (
        await start_import(
            client,
            hdrs,
            entity="PRODUCTS",
            payload=workbook_bytes([["Referencia", "Articulo"], ["MAR-01", "Martillo"]]),
        )
    ).json()["job"]
    await client.post(f"/api/v1/imports/{products_job['id']}/run", headers=hdrs)

    stock_job = (
        await start_import(
            client,
            hdrs,
            entity="STOCK",
            payload=workbook_bytes(
                [["Codigo", "Bodega", "Cantidad"], ["MAR-01", "Bodega Central", "25"]]
            ),
        )
    ).json()["job"]
    result = await client.post(f"/api/v1/imports/{stock_job['id']}/run", headers=hdrs)

    assert result.json()["stats"]["created"] == 1
    stock = (await client.get("/api/v1/inventory/stock", headers=hdrs)).json()
    assert Decimal(stock["items"][0]["quantity"]) == Decimal("25")

    movements = (await client.get("/api/v1/inventory/movements", headers=hdrs)).json()
    assert movements["total"] == 1
    assert movements["items"][0]["movement_type"] == "ADJUSTMENT"
    assert "Carga inicial" in movements["items"][0]["notes"]


async def test_stock_for_an_unknown_product_is_reported_not_invented(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    await create_warehouse(client, hdrs, "Bodega Central")
    job = (
        await start_import(
            client,
            hdrs,
            entity="STOCK",
            payload=workbook_bytes(
                [["Codigo", "Bodega", "Cantidad"], ["NO-EXISTE", "Bodega Central", "5"]]
            ),
        )
    ).json()["job"]

    result = (await client.post(f"/api/v1/imports/{job['id']}/run", headers=hdrs)).json()

    assert result["stats"]["skipped"] == 1
    assert "No existe la producto" in result["errors_preview"][0]["message"]


async def test_imports_are_invisible_across_tenants(client):
    hdrs_a, _ = await tenant(client, "a@example.com", "Acme")
    hdrs_b, _ = await tenant(client, "b@example.com", "Globex")
    job = (
        await start_import(
            client, hdrs_a, entity="PRODUCTS", payload=workbook_bytes(MESSY_PRODUCTS)
        )
    ).json()["job"]

    assert (await client.get(f"/api/v1/imports/{job['id']}", headers=hdrs_b)).status_code == 404
    assert (await client.get("/api/v1/imports", headers=hdrs_b)).json()["total"] == 0
    assert (
        await client.post(f"/api/v1/imports/{job['id']}/run", headers=hdrs_b)
    ).status_code == 404


async def test_a_finished_import_cannot_be_rerun(client, unique_email):
    hdrs, _ = await tenant(client, unique_email)
    job = (
        await start_import(client, hdrs, entity="PRODUCTS", payload=workbook_bytes(MESSY_PRODUCTS))
    ).json()["job"]
    await client.post(f"/api/v1/imports/{job['id']}/run", headers=hdrs)

    again = await client.post(f"/api/v1/imports/{job['id']}/run", headers=hdrs)

    assert again.status_code == 422
    assert again.json()["error"]["code"] == "IMPORT_NOT_OPEN"
