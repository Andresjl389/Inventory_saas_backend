"""Reading the file itself: layout problems before data problems."""

import io

import pytest
from openpyxl import Workbook

from app.domain.imports.exceptions import NoHeaderRowError
from app.infrastructure.imports.reader import read_table

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _workbook(rows) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_a_title_above_the_header_does_not_become_the_header():
    """Exported reports routinely open with a title in A1."""
    payload = _workbook(
        [
            ["Inventario al 31/12", None, None],
            [None, None, None],
            ["Código", "Nombre", "Precio"],
            ["MAR-01", "Martillo", 15000],
        ]
    )

    table = read_table(payload, XLSX)

    assert table.header_row == 3
    assert table.headers == ["Código", "Nombre", "Precio"]
    assert [number for number, _ in table.numbered()] == [4]


def test_blank_rows_between_data_are_skipped_without_shifting_row_numbers():
    payload = _workbook([["Código"], ["A-1"], [None], ["A-2"]])

    table = read_table(payload, XLSX)
    numbered = list(table.numbered())

    assert [row["Código"] for _, row in numbered] == ["A-1", "A-2"]


def test_duplicate_headers_do_not_silently_overwrite_each_other():
    payload = _workbook([["Precio", "Precio"], [1, 2]])

    table = read_table(payload, XLSX)

    assert table.headers == ["Precio", "Precio (2)"]
    assert list(table.numbered())[0][1] == {"Precio": 1, "Precio (2)": 2}


def test_an_unnamed_column_gets_a_position_name():
    payload = _workbook([["Código", None, "Precio"], ["A-1", "x", 2]])

    assert read_table(payload, XLSX).headers == ["Código", "Columna 2", "Precio"]


def test_a_file_with_nothing_in_it_is_refused():
    with pytest.raises(NoHeaderRowError):
        read_table(_workbook([[None, None]]), XLSX)


def test_a_semicolon_csv_in_latin1_is_read():
    payload = "nombre;documento\nJuan Pérez;900123\n".encode("latin-1")

    table = read_table(payload, "text/csv", "clientes.csv")

    assert table.headers == ["nombre", "documento"]
    assert list(table.numbered())[0][1]["nombre"] == "Juan Pérez"


def test_the_extension_is_trusted_when_the_content_type_is_not():
    """Browsers send application/octet-stream often enough to matter."""
    payload = _workbook([["Código"], ["A-1"]])

    assert read_table(payload, "application/octet-stream", "productos.xlsx").headers == ["Código"]


def test_samples_skip_empty_cells():
    payload = _workbook([["Precio"], [None], [15000], [None], [8000]])

    assert read_table(payload, XLSX).samples("Precio") == ["15000", "8000"]
