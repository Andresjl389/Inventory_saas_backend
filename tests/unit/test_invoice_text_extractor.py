"""El lector determinista: la parte del escaneo que sí se puede afirmar.

Las cifras colombianas son el punto: "15.000" son quince mil, y el lector las
pasa por el mismo `to_decimal` del importador de Excel en vez de inventar su
propia aritmética.
"""

from decimal import Decimal

import pytest

from app.domain.invoices.exceptions import UnsupportedInvoiceFileError
from app.infrastructure.invoices.text_extractor import TextInvoiceExtractor

INVOICE = """\
Proveedor: Distribuidora El Sol
NIT: 900.123.456-7
Factura: F-00123
Fecha: 15/10/2026
Total: 41.000
---
2 | ARROZ DIANA X500GR | 2.500
3 | ACEITE PREMIER 1L | 12.000 | 7702007037128
1 | Flete | 0
"""


async def read(document: str):
    return await TextInvoiceExtractor().extract(document.encode(), "text/plain", "factura.txt")


async def test_it_reads_the_header_and_every_line():
    invoice = await read(INVOICE)

    assert invoice.supplier_name == "Distribuidora El Sol"
    assert invoice.supplier_tax_id == "900.123.456-7"
    assert invoice.invoice_number == "F-00123"
    assert invoice.invoice_date.isoformat() == "2026-10-15"
    assert len(invoice.lines) == 3
    assert invoice.lines[1].code == "7702007037128"


async def test_colombian_thousands_are_read_as_thousands():
    invoice = await read(INVOICE)

    assert invoice.total == Decimal("41000")
    assert invoice.lines[0].unit_cost == Decimal("2500")
    assert invoice.lines[0].computed_total == Decimal("5000")


async def test_the_lines_adding_up_to_the_printed_total_is_what_proves_the_reading():
    invoice = await read(INVOICE)

    assert invoice.lines_total == Decimal("41000")
    assert invoice.total_mismatch == Decimal("0")


async def test_a_quantity_that_cannot_be_read_is_flagged_not_invented():
    invoice = await read("ilegible | ARROZ | 2.500\n")

    line = invoice.lines[0]
    assert line.quantity == Decimal("1")
    assert any("cantidad" in warning for warning in line.warnings)


async def test_an_unreadable_cost_stays_at_zero_and_says_so():
    """Inventar un precio sí falsea la compra, así que queda visible en cero."""
    invoice = await read("2 | ARROZ | ???\n")

    line = invoice.lines[0]
    assert line.unit_cost == Decimal("0")
    assert any("costo" in warning for warning in line.warnings)


async def test_an_incomplete_row_is_skipped_with_a_warning():
    invoice = await read("2 | ARROZ\n")

    assert invoice.lines == ()
    assert invoice.warnings


async def test_a_document_it_cannot_read_is_refused_instead_of_guessed():
    with pytest.raises(UnsupportedInvoiceFileError):
        await TextInvoiceExtractor().extract(b"\x89PNG", "image/png", "foto.png")
