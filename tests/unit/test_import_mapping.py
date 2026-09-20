"""Matching somebody's column headers to our fields."""

from app.domain.imports.mapping import normalise_header, suggest_mapping
from app.domain.imports.schemas import CUSTOMERS_SCHEMA, PRODUCTS_SCHEMA, ImportEntity, schema_for


def _targets(headers, schema=PRODUCTS_SCHEMA) -> dict[str, str | None]:
    return {item.source: item.target for item in suggest_mapping(headers, schema)}


def test_headers_are_compared_without_accents_case_or_punctuation():
    assert normalise_header("  Precio de Venta ") == "precio de venta"
    assert normalise_header("CÓDIGO_BARRAS") == "codigo barras"


def test_the_obvious_spanish_headers_map_themselves():
    mapping = _targets(["Código", "Nombre", "Precio de venta", "Costo", "Categoría"])

    assert mapping == {
        "Código": "sku",
        "Nombre": "name",
        "Precio de venta": "sale_price",
        "Costo": "cost_price",
        "Categoría": "category",
    }


def test_synonyms_from_other_systems_are_recognised():
    mapping = _targets(["referencia", "articulo", "pvp", "familia", "ean"])

    assert mapping["referencia"] == "sku"
    assert mapping["articulo"] == "name"
    assert mapping["pvp"] == "sale_price"
    assert mapping["familia"] == "category"
    assert mapping["ean"] == "barcode"


def test_a_column_we_do_not_recognise_is_left_for_the_user():
    mapping = _targets(["Código", "Centro de costo interno"])

    assert mapping["Código"] == "sku"
    assert mapping["Centro de costo interno"] is None


def test_a_target_is_never_proposed_twice():
    """Otherwise the import would depend on which column came first."""
    suggestions = suggest_mapping(["Precio", "Precio venta", "Precio (2)"], PRODUCTS_SCHEMA)
    targets = [item.target for item in suggestions if item.target]

    assert len(targets) == len(set(targets))


def test_the_best_match_wins_the_target():
    mapping = _targets(["descripcion", "nombre producto"])

    assert mapping["nombre producto"] == "name"
    assert mapping["descripcion"] == "description"


def test_customer_documents_are_recognised_by_local_names():
    mapping = _targets(["razón social", "NIT", "celular"], CUSTOMERS_SCHEMA)

    assert mapping["razón social"] == "name"
    assert mapping["NIT"] == "document_number"
    assert mapping["celular"] == "phone"


def test_every_schema_declares_a_key_field_that_exists():
    for entity in ImportEntity:
        schema = schema_for(entity)
        assert schema.by_key(schema.key_field) is not None, entity
