from decimal import Decimal

import pytest

from app.domain.purchases.entities.purchase import Purchase, PurchaseItem, PurchaseStatus
from app.domain.purchases.exceptions import (
    EmptyPurchaseError,
    InvalidPurchaseTransitionError,
)
from app.domain.sales.entities.sale import Sale, SaleItem, SaleStatus
from app.domain.sales.exceptions import (
    EmptySaleError,
    InvalidSaleItemError,
    InvalidSaleTransitionError,
)
from app.domain.shared.entities import new_id


def _sale(*lines: tuple[str, str, str, str]) -> Sale:
    company_id, sale_id = new_id(), new_id()
    items = [
        SaleItem(
            company_id=company_id,
            sale_id=sale_id,
            product_id=new_id(),
            quantity=Decimal(quantity),
            unit_price=Decimal(price),
            discount=Decimal(discount),
            tax=Decimal(tax),
        )
        for quantity, price, discount, tax in lines
    ]
    return Sale(id=sale_id, company_id=company_id, warehouse_id=new_id(), items=items)


def test_totals_are_derived_from_the_items():
    sale = _sale(("2", "10.00", "1.00", "0.50"), ("3", "5.00", "0", "0"))

    assert sale.subtotal == Decimal("35.0000")  # 20 + 15
    assert sale.discount == Decimal("1.0000")
    assert sale.tax == Decimal("0.5000")
    assert sale.total == Decimal("34.5000")


def test_a_line_discount_cannot_exceed_its_gross():
    with pytest.raises(InvalidSaleItemError):
        _sale(("1", "10.00", "11.00", "0"))


def test_zero_quantity_lines_are_rejected():
    with pytest.raises(InvalidSaleItemError):
        _sale(("0", "10.00", "0", "0"))


def test_a_sale_without_items_cannot_be_completed():
    sale = Sale(company_id=new_id(), warehouse_id=new_id())
    with pytest.raises(EmptySaleError):
        sale.complete()


def test_a_completed_sale_cannot_be_completed_again():
    sale = _sale(("1", "10.00", "0", "0"))
    sale.complete()
    with pytest.raises(InvalidSaleTransitionError):
        sale.complete()


def test_only_a_completed_sale_can_be_refunded():
    sale = _sale(("1", "10.00", "0", "0"))
    with pytest.raises(InvalidSaleTransitionError):
        sale.refund()

    sale.complete()
    sale.refund()
    assert sale.status is SaleStatus.REFUNDED


def test_a_cancelled_sale_is_final():
    sale = _sale(("1", "10.00", "0", "0"))
    sale.cancel()
    assert sale.status is SaleStatus.CANCELLED
    with pytest.raises(InvalidSaleTransitionError):
        sale.cancel()


def test_only_a_completed_sale_has_taken_stock():
    sale = _sale(("1", "10.00", "0", "0"))
    assert sale.affects_stock is False
    sale.complete()
    assert sale.affects_stock is True


def test_purchase_net_unit_cost_folds_discount_and_tax_back_in():
    company_id, purchase_id = new_id(), new_id()
    item = PurchaseItem(
        company_id=company_id,
        purchase_id=purchase_id,
        product_id=new_id(),
        quantity=Decimal("10"),
        unit_cost=Decimal("5.00"),
        discount=Decimal("5.00"),
        tax=Decimal("0"),
    )

    assert item.total == Decimal("45.0000")
    assert item.net_unit_cost == Decimal("4.5000")


def test_purchase_transitions_mirror_sales():
    purchase = Purchase(company_id=new_id(), warehouse_id=new_id())
    with pytest.raises(EmptyPurchaseError):
        purchase.complete()

    purchase.items.append(
        PurchaseItem(
            company_id=purchase.company_id,
            purchase_id=purchase.id,
            product_id=new_id(),
            quantity=Decimal("1"),
            unit_cost=Decimal("1"),
        )
    )
    purchase.recalculate_totals()
    purchase.complete()
    assert purchase.status is PurchaseStatus.COMPLETED

    with pytest.raises(InvalidPurchaseTransitionError):
        purchase.complete()
