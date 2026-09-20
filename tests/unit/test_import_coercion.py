"""Reading messy cells.

Every case here came from the shape real files arrive in: currency symbols,
Latin-American thousand separators, Excel turning a SKU into a float, "SÍ"
where a boolean belongs.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.imports.coercion import (
    CoercionError,
    CoercionOptions,
    FieldType,
    coerce,
    is_blank,
    to_boolean,
    to_date,
    to_decimal,
    to_integer,
    to_text,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$ 15.000", Decimal("15000")),  # punto de miles
        ("15,000", Decimal("15000")),  # coma de miles
        ("1.234,56", Decimal("1234.56")),  # es-CO
        ("1,234.56", Decimal("1234.56")),  # en-US
        ("1.234.567", Decimal("1234567")),
        ("12.50", Decimal("12.50")),
        ("12,50", Decimal("12.50")),
        ("1.5", Decimal("1.5")),
        ("  42  ", Decimal("42")),
        ("-8,25", Decimal("-8.25")),
    ],
)
def test_numbers_arrive_in_every_shape(raw, expected):
    assert to_decimal(raw) == expected


def test_a_three_digit_group_is_read_as_thousands():
    """15.000 is fifteen thousand far more often than it is fifteen."""
    assert to_decimal("15.000") == Decimal("15000")


def test_an_explicit_separator_overrides_the_guess():
    assert to_decimal("15.000", CoercionOptions(decimal_separator=".")) == Decimal("15.000")
    assert to_decimal("15,000", CoercionOptions(decimal_separator=",")) == Decimal("15.000")


@pytest.mark.parametrize("raw", ["abc", "CC-1", "10 unidades", "$", "-", "mil pesos"])
def test_text_is_never_salvaged_into_a_number(raw):
    """Stripping the letters out of "CC-1" would yield -1, which is worse than
    refusing: a wrong price imports silently."""
    if raw == "-":
        assert to_decimal(raw) is None  # a dash is one of the ways a cell says nothing
        return
    with pytest.raises(CoercionError):
        to_decimal(raw)


@pytest.mark.parametrize("raw", ["SÍ", "si", " X ", "TRUE", "1", "activo"])
def test_yes_in_the_ways_people_write_it(raw):
    assert to_boolean(raw) is True


@pytest.mark.parametrize("raw", ["NO", "false", "0", "inactivo"])
def test_no_in_the_ways_people_write_it(raw):
    assert to_boolean(raw) is False


def test_an_ambiguous_boolean_is_refused_rather_than_guessed():
    with pytest.raises(CoercionError):
        to_boolean("quizás")


@pytest.mark.parametrize("raw", ["", "  ", "N/A", "n/a", "-", "sin dato", None])
def test_the_ways_a_cell_says_nothing(raw):
    assert is_blank(raw)
    assert to_text(raw) is None
    assert to_decimal(raw) is None


def test_excel_floats_do_not_turn_a_code_into_a_decimal():
    """A SKU cell holding 4 comes back from openpyxl as 4.0."""
    assert to_text(4.0) == "4"
    assert to_text(4.5) == "4.5"


def test_non_breaking_spaces_from_copy_paste_are_normalised():
    assert to_text("MAR - 01 ") == "MAR - 01"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-12-31", date(2026, 12, 31)),
        ("31/12/2026", date(2026, 12, 31)),
        ("31-12-2026", date(2026, 12, 31)),
        ("2026/12/31", date(2026, 12, 31)),
    ],
)
def test_dates_in_the_usual_formats(raw, expected):
    assert to_date(raw) == expected


def test_a_decimal_that_is_not_whole_is_not_an_integer():
    assert to_integer("10") == 10
    with pytest.raises(CoercionError):
        to_integer("10,5")


def test_an_enum_is_matched_case_insensitively_and_bounded():
    assert coerce("nit", FieldType.ENUM, allowed=("NIT", "CC")) == "NIT"
    with pytest.raises(CoercionError) as excinfo:
        coerce("pasaporte", FieldType.ENUM, allowed=("NIT", "CC"))
    assert "NIT, CC" in str(excinfo.value)
