from decimal import Decimal

import pytest

from app.domain.inventory.entities.product_stock import ProductStock
from app.domain.inventory.entities.stock_movement import MovementType, StockMovement
from app.domain.inventory.exceptions import InsufficientStockError, InvalidMovementError
from app.domain.shared.entities import new_id


def _movement(**overrides) -> StockMovement:
    defaults = dict(
        company_id=new_id(),
        product_id=new_id(),
        warehouse_id=new_id(),
        movement_type=MovementType.PURCHASE,
        quantity=Decimal("5"),
    )
    return StockMovement(**{**defaults, **overrides})


def test_a_movement_of_zero_is_rejected():
    with pytest.raises(InvalidMovementError):
        _movement(quantity=Decimal("0"))


@pytest.mark.parametrize(
    "movement_type", [MovementType.PURCHASE, MovementType.RETURN, MovementType.TRANSFER_IN]
)
def test_incoming_movements_must_be_positive(movement_type):
    with pytest.raises(InvalidMovementError):
        _movement(movement_type=movement_type, quantity=Decimal("-1"))


@pytest.mark.parametrize("movement_type", [MovementType.SALE, MovementType.TRANSFER_OUT])
def test_outgoing_movements_must_be_negative(movement_type):
    with pytest.raises(InvalidMovementError):
        _movement(movement_type=movement_type, quantity=Decimal("1"))


def test_adjustments_accept_either_sign():
    assert _movement(movement_type=MovementType.ADJUSTMENT, quantity=Decimal("-3")).quantity < 0
    assert _movement(movement_type=MovementType.ADJUSTMENT, quantity=Decimal("3")).quantity > 0


def test_stock_cannot_go_negative():
    stock = ProductStock(
        company_id=new_id(), product_id=new_id(), warehouse_id=new_id(), quantity=Decimal("2")
    )
    with pytest.raises(InsufficientStockError) as excinfo:
        stock.apply(Decimal("-3"))

    assert excinfo.value.details["available"] == "2"
    assert stock.quantity == Decimal("2"), "a rejected movement must not mutate the row"


def test_stock_may_go_negative_when_explicitly_allowed():
    stock = ProductStock(company_id=new_id(), product_id=new_id(), warehouse_id=new_id())
    stock.apply(Decimal("-3"), allow_negative=True)
    assert stock.quantity == Decimal("-3")
