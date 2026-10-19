"""El libro del fiado: signos, saldo y cupo."""

from decimal import Decimal

import pytest

from app.domain.credit.entities.account import (
    AccountEntry,
    CustomerBalance,
    EntryType,
    PaymentMethod,
)
from app.domain.credit.exceptions import (
    CreditSaleNeedsCustomerError,
    InvalidAccountEntryError,
    OverpaidSaleError,
)
from app.domain.sales.entities.sale import Sale, SaleItem
from app.domain.shared.entities import new_id


def _entry(**overrides) -> AccountEntry:
    defaults = dict(
        company_id=new_id(),
        customer_id=new_id(),
        entry_type=EntryType.SALE,
        amount=Decimal("7400"),
    )
    return AccountEntry(**{**defaults, **overrides})


def _balance(amount="0") -> CustomerBalance:
    return CustomerBalance(company_id=new_id(), customer_id=new_id(), balance=Decimal(amount))


def test_a_movement_of_zero_is_rejected():
    with pytest.raises(InvalidAccountEntryError):
        _entry(amount=Decimal("0"))


def test_a_sale_increases_the_debt_and_must_be_positive():
    assert _entry().amount > 0
    with pytest.raises(InvalidAccountEntryError):
        _entry(entry_type=EntryType.SALE, amount=Decimal("-1"))


@pytest.mark.parametrize("entry_type", [EntryType.PAYMENT, EntryType.SALE_REVERSED])
def test_payments_and_reversals_reduce_the_debt(entry_type):
    assert _entry(entry_type=entry_type, amount=Decimal("-500")).amount < 0
    with pytest.raises(InvalidAccountEntryError):
        _entry(entry_type=entry_type, amount=Decimal("500"))


def test_an_adjustment_may_go_either_way():
    """Un perdón baja la deuda; pasar el cuaderno viejo la sube."""
    assert _entry(entry_type=EntryType.ADJUSTMENT, amount=Decimal("-2000")).amount < 0
    assert _entry(entry_type=EntryType.ADJUSTMENT, amount=Decimal("2000")).amount > 0


def test_the_balance_is_the_running_sum():
    balance = _balance()
    balance.apply(Decimal("7400"))
    balance.apply(Decimal("-2400"))
    assert balance.balance == Decimal("5000.0000")
    assert balance.owes


def test_a_zero_credit_limit_means_no_limit():
    balance = _balance("500000")
    assert balance.would_exceed(Decimal("999999"), Decimal("0")) is False
    assert balance.would_exceed(Decimal("1"), Decimal("500000")) is True
    assert balance.would_exceed(Decimal("1"), Decimal("500001")) is False


def _sale(total_units="2", price="3700", with_customer=True) -> Sale:
    company_id, sale_id = new_id(), new_id()
    item = SaleItem(
        company_id=company_id,
        sale_id=sale_id,
        product_id=new_id(),
        quantity=Decimal(total_units),
        unit_price=Decimal(price),
    )
    return Sale(
        id=sale_id,
        company_id=company_id,
        warehouse_id=new_id(),
        customer_id=new_id() if with_customer else None,
        items=[item],
    )


def test_cash_without_an_amount_pays_the_whole_sale():
    sale = _sale()
    sale.settle(PaymentMethod.CASH, None)
    assert sale.amount_paid == sale.total
    assert sale.outstanding == Decimal("0.0000")
    assert sale.is_on_credit is False


def test_credit_without_an_amount_pays_nothing():
    sale = _sale()
    sale.settle(PaymentMethod.CREDIT, None)
    assert sale.amount_paid == Decimal("0")
    assert sale.outstanding == sale.total
    assert sale.is_on_credit


def test_a_partial_payment_leaves_the_rest_on_the_account():
    """«Le doy 5 mil y le quedo debiendo» -- el caso corriente del mostrador."""
    sale = _sale()
    sale.settle(PaymentMethod.CASH, Decimal("5000"))
    assert sale.outstanding == Decimal("2400.0000")
    assert sale.is_on_credit


def test_you_cannot_pay_more_than_the_sale():
    sale = _sale()
    with pytest.raises(OverpaidSaleError):
        sale.settle(PaymentMethod.CASH, Decimal("99999"))


def test_you_cannot_lend_to_nobody():
    sale = _sale(with_customer=False)
    with pytest.raises(CreditSaleNeedsCustomerError):
        sale.settle(PaymentMethod.CREDIT, None)

    # De contado sin cliente sí: el mostrador no pide nombre.
    sale.settle(PaymentMethod.CASH, None)
    assert sale.is_on_credit is False


def test_a_negative_balance_means_the_shop_owes_the_customer():
    """Pasa al devolver una venta que el cliente ya había abonado en parte."""
    balance = _balance("-5000")

    assert balance.owes is False
    assert balance.in_favor == Decimal("5000")
    assert _balance("2400").in_favor == Decimal("0")
