"""Las reglas del escaneo, sin base de datos.

La regla que importa: ningún renglón entra solo. Todo lo demás en el módulo
existe para sostener esa.
"""

import uuid
from decimal import Decimal

import pytest

from app.domain.invoices.entities.scan import (
    InvalidScanLineError,
    InvoiceScan,
    LineAction,
    ScanLine,
    ScanStatus,
)
from app.domain.invoices.exceptions import (
    NothingToPurchaseError,
    ScanNotOpenError,
    UndecidedLinesError,
    WarehouseRequiredError,
)
from app.domain.invoices.matching import ProductMatch

COMPANY = uuid.uuid4()
PRODUCT = uuid.uuid4()


def line(**fields) -> ScanLine:
    defaults = {
        "company_id": COMPANY,
        "scan_id": SCAN_ID,
        "line_number": 1,
        "description": "ARROZ DIANA X500GR",
        "quantity": Decimal("2"),
        "unit_cost": Decimal("2500"),
    }
    return ScanLine(**{**defaults, **fields})


SCAN_ID = uuid.uuid4()


def scan(*lines: ScanLine, **fields) -> InvoiceScan:
    defaults = {
        "id": SCAN_ID,
        "company_id": COMPANY,
        "file_id": uuid.uuid4(),
        "filename": "factura.jpg",
    }
    return InvoiceScan(**{**defaults, **fields}, lines=list(lines))


def test_a_certain_suggestion_links_the_line_by_itself():
    item = line()

    item.apply_suggestion(ProductMatch(product_id=PRODUCT, confidence=0.97, reason="similar"))

    assert item.action is LineAction.LINK
    assert item.product_id == PRODUCT


def test_an_uncertain_suggestion_is_recorded_but_left_pending():
    item = line()

    item.apply_suggestion(ProductMatch(product_id=PRODUCT, confidence=0.7, reason="similar"))

    assert item.action is LineAction.PENDING
    assert item.product_id is None
    assert item.suggested_product_id == PRODUCT
    assert item.needs_review


def test_deciding_to_skip_drops_the_product_it_was_pointing_at():
    """Un renglón descartado que arrastre el producto crearía una compra que
    nadie pidió."""
    item = line()
    item.apply_suggestion(ProductMatch(product_id=PRODUCT, confidence=1.0, reason="exact"))

    item.decide(LineAction.SKIP)

    assert item.product_id is None
    assert not item.is_merchandise


def test_linking_without_saying_to_what_is_refused():
    with pytest.raises(InvalidScanLineError):
        line().decide(LineAction.LINK)


def test_a_line_whose_printed_total_does_not_add_up_asks_for_review():
    item = line(declared_total=Decimal("6000"))

    assert item.total == Decimal("5000")
    assert item.total_mismatch == Decimal("1000")
    assert item.needs_review


def test_a_line_cannot_be_saved_with_a_quantity_of_zero():
    with pytest.raises(InvalidScanLineError):
        line(quantity=Decimal("0"))


def test_a_line_cannot_be_saved_without_a_description():
    with pytest.raises(InvalidScanLineError):
        line(description="   ")


def test_a_pending_line_blocks_the_confirmation():
    document = scan(line(), warehouse_id=uuid.uuid4())

    with pytest.raises(UndecidedLinesError):
        document.confirm(uuid.uuid4())

    assert document.status is ScanStatus.EXTRACTED


def test_confirming_without_a_warehouse_is_refused():
    decided = line()
    decided.decide(LineAction.LINK, product_id=PRODUCT)

    with pytest.raises(WarehouseRequiredError):
        scan(decided).confirm(uuid.uuid4())


def test_a_scan_where_everything_was_discarded_has_nothing_to_buy():
    discarded = line()
    discarded.decide(LineAction.SKIP)

    with pytest.raises(NothingToPurchaseError):
        scan(discarded, warehouse_id=uuid.uuid4()).confirm(uuid.uuid4())


def test_discarded_lines_do_not_count_towards_the_total():
    kept = line(line_number=1)
    kept.decide(LineAction.LINK, product_id=PRODUCT)
    freight = line(line_number=2, description="FLETE", quantity=Decimal("1"))
    freight.decide(LineAction.SKIP)

    document = scan(kept, freight, declared_total=Decimal("8000"))

    assert document.lines_total == Decimal("5000")
    # La diferencia no es un error: es el flete que alguien descartó, y es
    # justo lo que la pantalla tiene que poder explicar.
    assert document.total_mismatch == Decimal("3000")


def test_confirming_closes_the_scan_and_a_closed_scan_rejects_changes():
    decided = line()
    decided.decide(LineAction.LINK, product_id=PRODUCT)
    document = scan(decided, warehouse_id=uuid.uuid4())
    purchase_id = uuid.uuid4()

    document.confirm(purchase_id)

    assert document.status is ScanStatus.CONFIRMED
    assert document.purchase_id == purchase_id
    with pytest.raises(ScanNotOpenError):
        document.confirm(uuid.uuid4())
    with pytest.raises(ScanNotOpenError):
        document.cancel()


def test_a_created_product_is_linked_and_leaves_a_trace_of_where_it_came_from():
    item = line()
    item.decide(LineAction.CREATE, new_product={"sale_price": "3000"})

    item.link_created_product(PRODUCT, sku="ARROZ-DIANA-500G")

    assert item.action is LineAction.LINK
    assert item.product_id == PRODUCT
    assert item.new_product["created_product_id"] == str(PRODUCT)
    assert item.new_product["created_sku"] == "ARROZ-DIANA-500G"
    # Lo que pidió la persona no se pierde al cumplirse.
    assert item.new_product["sale_price"] == "3000"
