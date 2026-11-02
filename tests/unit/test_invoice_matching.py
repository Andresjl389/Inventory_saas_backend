"""Emparejar la descripción de una factura con un producto del catálogo.

Lo que se prueba aquí no es "que acierte": es que acierte *solo* cuando está
seguro. Un enlace automático equivocado mete mercancía ajena al inventario sin
que nadie lo note, así que el umbral alto es la prueba, no el detalle.
"""

import uuid

from app.domain.invoices.matching import (
    AUTO_LINK,
    MIN_CONFIDENCE,
    ProductCandidate,
    match_product,
)

ARROZ = uuid.UUID("11111111-1111-1111-1111-111111111111")
ACEITE = uuid.UUID("22222222-2222-2222-2222-222222222222")
AGUARDIENTE = uuid.UUID("33333333-3333-3333-3333-333333333333")

CATALOG = [
    ProductCandidate(
        product_id=ARROZ, name="Arroz Diana 500 g", sku="ARR-500", barcode="7702007037128"
    ),
    ProductCandidate(product_id=ACEITE, name="Aceite Premier 1 L", sku="ACE-1L"),
    ProductCandidate(product_id=AGUARDIENTE, name="Aguardiente Antioqueño 750", sku="AGU-750"),
]


def test_an_abbreviated_description_still_finds_its_product():
    match = match_product("ARROZ DIANA X500GR", CATALOG)

    assert match.product_id == ARROZ
    assert match.is_certain


def test_the_printed_barcode_wins_over_the_text():
    """El código impreso es la única parte del papel que no es ambigua."""
    match = match_product("MERCANCIA VARIA", CATALOG, code="7702007037128")

    assert match.product_id == ARROZ
    assert match.confidence == 1.0
    assert match.reason == "barcode"


def test_the_printed_sku_also_wins():
    match = match_product("sin nombre util", CATALOG, code="ACE-1L")

    assert match.product_id == ACEITE
    assert match.reason == "sku"


def test_a_short_code_is_ignored_instead_of_matched_by_luck():
    """Un código de dos letras cabe dentro de cualquier cosa por casualidad."""
    match = match_product("algo que no existe en el catalogo", CATALOG, code="AC")

    assert match.product_id is None


def test_a_product_that_merely_starts_the_same_is_not_a_match():
    """ "AGUA" vive dentro de "AGUARDIENTE" y no son lo mismo."""
    match = match_product("AGUA CRISTAL BOTELLA 600", CATALOG)

    assert match.product_id is None
    assert match.reason == "unmatched"


def test_a_plausible_but_uncertain_match_is_proposed_and_not_linked():
    match = match_product("ACEITE 1 L", CATALOG)

    assert match.product_id == ACEITE
    assert MIN_CONFIDENCE <= match.confidence < AUTO_LINK
    assert not match.is_certain


def test_matching_does_not_depend_on_the_order_of_the_catalogue():
    forwards = match_product("ARROZ DIANA 500", CATALOG)
    backwards = match_product("ARROZ DIANA 500", list(reversed(CATALOG)))

    assert forwards == backwards


def test_an_empty_description_matches_nothing():
    assert match_product("   ", CATALOG).product_id is None
