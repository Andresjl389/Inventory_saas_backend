"""The downloadable template.

The simple path for a company is: download this, fill it, upload it. Because
the headers are the field labels, the mapping step then resolves to an exact
match on every column and the user never has to think about it.

A second sheet documents each field, so the template explains itself without a
manual next to it.
"""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app.domain.imports.coercion import FieldType
from app.domain.imports.schemas import EntitySchema

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
REQUIRED_FILL = PatternFill("solid", fgColor="C00000")
HEADER_FONT = Font(color="FFFFFF", bold=True)
MIN_WIDTH, MAX_WIDTH = 14, 42


def _autosize(sheet, values_by_column: list[list[str]]) -> None:
    for index, values in enumerate(values_by_column, start=1):
        longest = max((len(value) for value in values), default=0)
        sheet.column_dimensions[get_column_letter(index)].width = max(
            MIN_WIDTH, min(MAX_WIDTH, longest + 4)
        )


def build_template(schema: EntitySchema) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = schema.label[:31]

    for index, spec in enumerate(schema.fields, start=1):
        cell = sheet.cell(row=1, column=index)
        # The asterisk is the only cue most people need; the second sheet has
        # the detail for the ones who look.
        cell.value = f"{spec.label}*" if spec.required else spec.label
        cell.font = HEADER_FONT
        cell.fill = REQUIRED_FILL if spec.required else HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")

        if spec.example:
            sheet.cell(row=2, column=index).value = spec.example

        if spec.type is FieldType.ENUM and spec.enum_values:
            rule = DataValidation(
                type="list",
                formula1=f'"{",".join(spec.enum_values)}"',
                allow_blank=not spec.required,
                showDropDown=False,
            )
            sheet.add_data_validation(rule)
            letter = get_column_letter(index)
            rule.add(f"{letter}2:{letter}1000")

    sheet.freeze_panes = "A2"
    _autosize(
        sheet,
        [[spec.label, spec.example] for spec in schema.fields],
    )

    guide = workbook.create_sheet("Instrucciones")
    guide.append(["Campo", "Obligatorio", "Tipo", "Ejemplo", "Notas"])
    for cell in guide[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    guide.append([schema.label, "", "", "", schema.description])
    guide.append([])
    for spec in schema.fields:
        guide.append(
            [
                spec.label,
                "Sí" if spec.required else "No",
                _type_label(spec),
                spec.example,
                spec.help,
            ]
        )
    guide.append([])
    guide.append(
        [
            "Fila 2",
            "",
            "",
            "",
            "Contiene un ejemplo: bórrala antes de cargar o quedará importada.",
        ]
    )
    guide.append(
        [
            "Columnas",
            "",
            "",
            "",
            "Puedes renombrarlas o reordenarlas: al cargar eliges qué columna alimenta cada campo.",
        ]
    )
    for row in guide.iter_rows(min_row=1):
        row[-1].alignment = Alignment(wrap_text=True, vertical="top")
    _autosize(guide, [["Campo" * 3], ["Obligatorio"], ["Tipo" * 3], ["Ejemplo" * 3], ["Notas" * 8]])

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _type_label(spec) -> str:
    if spec.type is FieldType.ENUM:
        return " / ".join(spec.enum_values)
    return {
        FieldType.TEXT: "Texto",
        FieldType.DECIMAL: "Número",
        FieldType.INTEGER: "Número entero",
        FieldType.BOOLEAN: "Sí / No",
        FieldType.DATE: "Fecha",
    }[spec.type]


def build_onboarding_workbook() -> bytes:
    """One workbook with a sheet per entity, in the order they must be loaded.

    This is the operator's tool: a whole company's starting data in one file.
    Sheet names match the entity labels, which is how the loader finds them, so
    a sheet left empty is simply skipped.
    """
    from app.domain.imports.schemas import RECOMMENDED_ORDER, schema_for

    workbook = Workbook()
    workbook.remove(workbook.active)

    guide = workbook.create_sheet("Léeme", 0)
    guide.append(["Carga inicial de una empresa"])
    guide["A1"].font = Font(bold=True, size=14)
    guide.append([])
    guide.append(["Hoja", "Contenido", "Obligatorio"])
    for cell in guide[3]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for position, entity in enumerate(RECOMMENDED_ORDER, start=1):
        schema = schema_for(entity)
        guide.append(
            [
                schema.label,
                schema.description,
                ", ".join(spec.label for spec in schema.fields if spec.required),
            ]
        )

        sheet = workbook.create_sheet(schema.label[:31], position)
        for index, spec in enumerate(schema.fields, start=1):
            cell = sheet.cell(row=1, column=index)
            cell.value = f"{spec.label}*" if spec.required else spec.label
            cell.font = HEADER_FONT
            cell.fill = REQUIRED_FILL if spec.required else HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center")
        sheet.freeze_panes = "A2"
        _autosize(sheet, [[spec.label, spec.example] for spec in schema.fields])

    guide.append([])
    guide.append(
        [
            "Orden",
            "Las hojas se cargan de izquierda a derecha: una hoja puede "
            "depender de la anterior (un producto de su categoría, el stock "
            "del producto y la bodega).",
        ]
    )
    guide.append(["Hojas vacías", "Se omiten. Puedes cargar solo las que te interesen."])
    for row in guide.iter_rows(min_row=1):
        for cell in row[1:]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    _autosize(guide, [["Hoja" * 4], ["Contenido" * 8], ["Obligatorio" * 3]])

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
