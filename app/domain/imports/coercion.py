"""Turning messy spreadsheet cells into typed values.

This is where most of the value of the importer lives. Real files carry
"$ 1.234,56", "1,234.56", " SÍ ", "N/A", dates as text in four formats and
numbers Excel already turned into floats. Guessing wrong silently is worse than
refusing, so every coercion either returns a value or raises with a message the
user can act on.
"""

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

# Cells that mean "nothing here", whatever the person typed.
BLANK_VALUES = frozenset(
    {"", "-", "--", "n/a", "na", "null", "none", "ninguno", "sin dato", "s/d", "#n/a"}
)

TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y", "si", "sí", "s", "x", "verdadero", "activo"})
FALSE_VALUES = frozenset({"0", "false", "f", "no", "n", "falso", "inactivo"})

# Currency symbols and the spaces Excel likes to hide inside numbers.
_CURRENCY = re.compile(r"[$€£¥\s  ]")
_NUMERIC_KEEP = re.compile(r"[^0-9,.\-+]")

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M",
)


class FieldType(StrEnum):
    TEXT = "TEXT"
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    ENUM = "ENUM"


class CoercionError(ValueError):
    """The cell could not be read as the target type."""


@dataclass(frozen=True, slots=True)
class CoercionOptions:
    """Per-import overrides for the ambiguous cases.

    `decimal_separator=None` means "work it out per value", which is right for
    a mixed file and wrong for one where 1.500 means one thousand five hundred.
    Saying so explicitly is the difference between importing 1500 and 1.5.
    """

    decimal_separator: str | None = None
    date_format: str | None = None
    trim: bool = True


# Shared because CoercionOptions is frozen: one instance for every call site
# that does not override anything.
DEFAULT_OPTIONS = CoercionOptions()


def is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().lower() in BLANK_VALUES


def to_text(value: object, options: CoercionOptions = DEFAULT_OPTIONS) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        # Excel hands back 4.0 for a cell showing 4; a SKU must not become "4.0".
        text = str(int(value))
    elif isinstance(value, datetime | date):
        text = value.isoformat()
    else:
        text = str(value)
    # Non-breaking spaces survive copy-paste from the web and break every
    # later comparison; normalise them here once.
    text = text.replace(" ", " ").replace(" ", " ")
    return text.strip() if options.trim else text


def _normalise_number(raw: str, options: CoercionOptions) -> str:
    cleaned = _CURRENCY.sub("", raw)
    if any(character.isalpha() for character in cleaned):
        # Stripping non-numeric characters would turn "CC-1" into -1 and
        # "10 unidades" into 10. A cell with letters in it is not a number, and
        # guessing one from it is worse than saying so.
        raise CoercionError(f"{raw!r} is not a number")

    cleaned = _NUMERIC_KEEP.sub("", cleaned)
    if not cleaned or not any(character.isdigit() for character in cleaned):
        raise CoercionError(f"{raw!r} is not a number")

    separator = options.decimal_separator
    if separator is None:
        separator = _guess_separator(cleaned)
    if separator is None:
        return cleaned

    thousands = "." if separator == "," else ","
    return cleaned.replace(thousands, "").replace(separator, ".")


def _guess_separator(cleaned: str) -> str | None:
    """Work out which of . and , is the decimal point.

    Three cases, in order:

    * both present -> the last one is the decimal point, so 1.234,56 and
      1,234.56 both come out right;
    * one of them, repeated -> it groups thousands (1.234.567);
    * one of them, once, with exactly three digits after it -> ambiguous.
      15.000 is fifteen thousand far more often than it is fifteen, so it is
      read as a thousands separator. A file where that is wrong should set
      `decimal_separator` explicitly; the preview is there to catch it.
    """
    last_comma, last_dot = cleaned.rfind(","), cleaned.rfind(".")
    if last_comma == -1 and last_dot == -1:
        return None
    if last_comma != -1 and last_dot != -1:
        return "," if last_comma > last_dot else "."

    separator = "," if last_comma != -1 else "."
    if cleaned.count(separator) > 1:
        return "." if separator == "," else ","

    digits_after = len(cleaned) - cleaned.rfind(separator) - 1
    if digits_after == 3:
        return "." if separator == "," else ","
    return separator


def to_decimal(value: object, options: CoercionOptions = DEFAULT_OPTIONS) -> Decimal | None:
    if is_blank(value):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        return Decimal(str(value))

    try:
        return Decimal(_normalise_number(str(value), options))
    except (InvalidOperation, CoercionError) as exc:
        raise CoercionError(f"{value!r} is not a valid number") from exc


def to_integer(value: object, options: CoercionOptions = DEFAULT_OPTIONS) -> int | None:
    number = to_decimal(value, options)
    if number is None:
        return None
    if number != number.to_integral_value():
        raise CoercionError(f"{value!r} is not a whole number")
    return int(number)


def to_boolean(value: object, options: CoercionOptions = DEFAULT_OPTIONS) -> bool | None:
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return value
    text = (to_text(value, options) or "").lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise CoercionError(f"{value!r} is not a yes/no value")


def to_date(value: object, options: CoercionOptions = DEFAULT_OPTIONS) -> date | None:
    if is_blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = to_text(value, options) or ""
    formats = (options.date_format,) if options.date_format else DATE_FORMATS
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CoercionError(f"{value!r} is not a date the importer recognises")


def to_enum(
    value: object,
    allowed: tuple[str, ...],
    options: CoercionOptions = DEFAULT_OPTIONS,
) -> str | None:
    if is_blank(value):
        return None
    text = (to_text(value, options) or "").upper().replace(" ", "_")
    if text not in allowed:
        raise CoercionError(f"{value!r} must be one of: {', '.join(allowed)}")
    return text


def coerce(
    value: object,
    field_type: FieldType,
    *,
    allowed: tuple[str, ...] = (),
    options: CoercionOptions = DEFAULT_OPTIONS,
) -> object | None:
    if field_type is FieldType.ENUM:
        return to_enum(value, allowed, options)
    return {
        FieldType.TEXT: to_text,
        FieldType.DECIMAL: to_decimal,
        FieldType.INTEGER: to_integer,
        FieldType.BOOLEAN: to_boolean,
        FieldType.DATE: to_date,
    }[field_type](value, options)
