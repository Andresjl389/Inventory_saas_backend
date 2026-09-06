from decimal import Decimal

import pytest

from app.domain.products.entities.product import Product
from app.domain.products.exceptions import InvalidProductPriceError
from app.domain.shared.entities import new_id


def _product(**overrides) -> Product:
    defaults = dict(company_id=new_id(), name="Widget", sku="wid-1")
    return Product(**{**defaults, **overrides})


def test_sku_is_normalised_to_uppercase():
    assert _product(sku=" wid-1 ").sku == "WID-1"


def test_negative_cost_price_is_rejected():
    with pytest.raises(InvalidProductPriceError):
        _product(cost_price=Decimal("-1"))


def test_update_prices_validates_before_committing():
    product = _product(cost_price=Decimal("10"), sale_price=Decimal("15"))
    with pytest.raises(InvalidProductPriceError):
        product.update_prices(cost_price=Decimal("-5"), sale_price=None)


def test_margin_uses_decimal_arithmetic():
    product = _product(cost_price=Decimal("10.10"), sale_price=Decimal("15.35"))
    assert product.margin == Decimal("5.25")


def test_deactivate_marks_inactive_and_touches_timestamp():
    product = _product()
    before = product.updated_at
    product.deactivate()
    assert product.is_active is False
    assert product.updated_at >= before
