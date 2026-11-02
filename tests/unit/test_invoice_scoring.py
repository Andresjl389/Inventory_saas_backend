"""Medir la lectura contra la verdad.

Es el instrumento con el que se decide si el modelo propio alcanza, así que lo
que importa es que no se engañe a sí mismo: un renglón que falta no puede
contar como medio acierto.
"""

from app.domain.invoices.scoring import score_header, score_lines, score_reading

TRUTH = {
    "supplier_name": "Distribuidora El Sol",
    "supplier_tax_id": "900.123.456-7",
    "invoice_number": "F-00123",
    "invoice_date": "2026-10-15",
    "total": "41000",
    "lines": [
        {"description": "ARROZ DIANA X500GR", "quantity": "2", "unit_cost": "2500"},
        {"description": "ACEITE PREMIER 1L", "quantity": "3", "unit_cost": "12000"},
    ],
}


def test_a_perfect_reading_is_clean():
    score = score_reading(dict(TRUTH), TRUTH)

    assert score.is_clean
    assert score.header_accuracy == 1.0
    assert score.lines.accuracy == 1.0


def test_case_and_accents_are_not_mistakes():
    """«DISTRIBUIDORA EL SOL» y «Distribuidora El Sol» son el mismo proveedor."""
    read = {**TRUTH, "supplier_name": "DISTRIBUIDORA EL SOL"}

    assert score_header(read, TRUTH)["supplier_name"]


def test_the_total_is_compared_as_a_number():
    assert score_header({**TRUTH, "total": "41000.0000"}, TRUTH)["total"]


def test_a_field_the_paper_did_not_have_is_not_charged_to_the_model():
    truth = {**TRUTH, "supplier_tax_id": None}

    assert "supplier_tax_id" not in score_header({**TRUTH}, truth)


def test_a_line_with_the_wrong_cost_counts_as_partial_not_exact():
    read = [
        {"description": "ARROZ DIANA X500GR", "quantity": "2", "unit_cost": "2500"},
        {"description": "ACEITE PREMIER 1L", "quantity": "3", "unit_cost": "1200"},
    ]

    score = score_lines(read, TRUTH["lines"])

    assert (score.exact, score.partial, score.missed, score.extra) == (1, 1, 0, 0)
    # Media factura bien leída no es una factura bien leída.
    assert score.accuracy == 0.5


def test_a_missing_line_is_counted_as_missing():
    score = score_lines([TRUTH["lines"][0]], TRUTH["lines"])

    assert score.missed == 1
    assert score.expected == 2


def test_an_invented_line_is_counted_as_extra():
    score = score_lines(
        [*TRUTH["lines"], {"description": "FANTASMA", "quantity": "1", "unit_cost": "1"}],
        TRUTH["lines"],
    )

    assert score.extra == 1
    assert score.exact == 2


def test_two_identical_lines_are_not_one_match_counted_twice():
    """Pasa de verdad: dos cajas del mismo producto a precios distintos."""
    truth = [
        {"description": "ARROZ DIANA", "quantity": "2", "unit_cost": "2500"},
        {"description": "ARROZ DIANA", "quantity": "1", "unit_cost": "2600"},
    ]

    score = score_lines([truth[0]], truth)

    assert score.exact == 1
    assert score.missed == 1
