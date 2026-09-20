"""Reading whatever the customer sends.

Handles .xlsx and .csv, and the ways a real file differs from a clean one:
byte-order marks, latin-1 encodings, semicolon delimiters, blank leading rows,
duplicate and empty headers, and trailing rows that Excel thinks exist because
somebody once clicked on them.
"""

import csv
import io

from openpyxl import load_workbook

from app.domain.imports.exceptions import (
    ImportTooLargeError,
    NoHeaderRowError,
    UnreadableFileError,
)
from app.domain.imports.table import SpreadsheetTable

# One import is a single transaction; beyond this the right answer is to split
# the file rather than hold a very long write open.
MAX_ROWS = 20_000
HEADER_SEARCH_LIMIT = 10

XLSX_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }
)
CSV_TYPES = frozenset({"text/csv", "text/plain", "application/csv"})
ENCODINGS = ("utf-8-sig", "utf-8", "latin-1")


def _clean_headers(raw: list[object]) -> list[str]:
    """Blank columns get a position name; duplicates get a suffix.

    Both happen constantly in exported files, and both would otherwise make one
    column silently overwrite another when the row becomes a dict.
    """
    seen: dict[str, int] = {}
    headers: list[str] = []
    for index, value in enumerate(raw):
        text = str(value).strip() if value is not None else ""
        text = text.replace(" ", " ").strip()
        if not text:
            text = f"Columna {index + 1}"
        if text in seen:
            seen[text] += 1
            text = f"{text} ({seen[text]})"
        else:
            seen[text] = 1
        headers.append(text)
    return headers


def _is_empty(values: list[object]) -> bool:
    return all(value is None or str(value).strip() == "" for value in values)


def _filled(values: list[object]) -> int:
    return sum(1 for value in values if value is not None and str(value).strip())


TEXT_ROW_BONUS = 2


def _header_score(values: list[object]) -> int:
    """How much a row looks like a header.

    Width alone is not enough: a header with one empty column would lose to the
    data row under it. Headers are also all text, so a row whose filled cells
    are none of them numbers or dates scores higher. Between equals, the
    earliest row wins -- which is what settles an all-text CSV.
    """
    filled = _filled(values)
    if not filled:
        return 0

    all_text = all(
        isinstance(value, str) and not _looks_numeric(value)
        for value in values
        if value is not None and str(value).strip()
    )
    return filled + (TEXT_ROW_BONUS if all_text else 0)


def _looks_numeric(value: str) -> bool:
    return value.strip().replace(".", "").replace(",", "").replace("-", "").isdigit()


def _find_header_row(matrix: list[list[object]]) -> int | None:
    """The best-looking header near the top.

    Exported files routinely open with a report title in A1 and a blank line
    under it, so the first non-empty row is often the wrong answer.
    """
    best_index, best_score = None, 0
    for index, row in enumerate(matrix[:HEADER_SEARCH_LIMIT]):
        score = _header_score(row)
        if score > best_score:
            best_index, best_score = index, score
    return best_index


def _table_from_matrix(matrix: list[list[object]]) -> SpreadsheetTable:
    header_index = _find_header_row(matrix)
    if header_index is None:
        raise NoHeaderRowError()

    # Trailing empties come from cells Excel considers "used"; they would
    # become "Columna 7", "Columna 8"... in the mapping screen.
    header_values = list(matrix[header_index])
    while header_values and not str(header_values[-1] or "").strip():
        header_values.pop()

    headers = _clean_headers(header_values)
    rows: list[dict[str, object]] = []
    for values in matrix[header_index + 1 :]:
        if _is_empty(values):
            continue
        padded = list(values) + [None] * (len(headers) - len(values))
        rows.append(dict(zip(headers, padded[: len(headers)], strict=True)))
        if len(rows) > MAX_ROWS:
            raise ImportTooLargeError(
                f"An import accepts at most {MAX_ROWS:,} rows; split the file",
                details={"max_rows": MAX_ROWS},
            )

    return SpreadsheetTable(headers=headers, rows=rows, header_row=header_index + 1)


def _read_xlsx(payload: bytes) -> SpreadsheetTable:
    try:
        workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    except Exception as exc:
        raise UnreadableFileError("That file is not a readable .xlsx workbook") from exc

    try:
        sheet = workbook[workbook.sheetnames[0]]
        matrix = [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()

    return _table_from_matrix(matrix)


def _decode(payload: bytes) -> str:
    for encoding in ENCODINGS:
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnreadableFileError("The file's text encoding could not be determined")


def _read_csv(payload: bytes) -> SpreadsheetTable:
    text = _decode(payload)
    sample = text[:8192]
    try:
        # Latin-American exports use ';' as often as ','.
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    matrix = [list(row) for row in csv.reader(io.StringIO(text), dialect)]
    if not matrix:
        raise NoHeaderRowError()
    return _table_from_matrix(matrix)


def read_all_sheets(payload: bytes) -> dict[str, SpreadsheetTable]:
    """Every sheet of a workbook, keyed by name.

    An onboarding workbook carries one sheet per entity; a sheet that has no
    header row is skipped rather than failing the whole file, because a user
    who left one blank meant to skip it.
    """
    try:
        workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    except Exception as exc:
        raise UnreadableFileError("That file is not a readable .xlsx workbook") from exc

    tables: dict[str, SpreadsheetTable] = {}
    try:
        for name in workbook.sheetnames:
            matrix = [list(row) for row in workbook[name].iter_rows(values_only=True)]
            try:
                tables[name] = _table_from_matrix(matrix)
            except NoHeaderRowError:
                continue
    finally:
        workbook.close()

    return tables


def read_table(payload: bytes, content_type: str, filename: str = "") -> SpreadsheetTable:
    normalised = (content_type or "").split(";")[0].strip().lower()
    lowered = filename.lower()

    if normalised in XLSX_TYPES or lowered.endswith((".xlsx", ".xlsm")):
        return _read_xlsx(payload)
    if normalised in CSV_TYPES or lowered.endswith((".csv", ".txt")):
        return _read_csv(payload)

    # Content types from browsers are unreliable; try both before giving up.
    try:
        return _read_xlsx(payload)
    except UnreadableFileError:
        return _read_csv(payload)


class OpenpyxlSpreadsheetReader:
    """The SpreadsheetReader port, backed by openpyxl and the csv module."""

    def read(self, payload: bytes, content_type: str, filename: str = "") -> SpreadsheetTable:
        return read_table(payload, content_type, filename)

    def read_all_sheets(self, payload: bytes) -> dict[str, SpreadsheetTable]:
        return read_all_sheets(payload)
