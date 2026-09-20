"""Turning raw spreadsheet rows into typed, validated records.

Everything that can go wrong with a cell is reported against the row and column
the user sees in their file, so the feedback is actionable without them having
to guess which of their columns we meant.
"""

from dataclasses import dataclass, field

from app.domain.imports.coercion import CoercionError, CoercionOptions, coerce
from app.domain.imports.schemas import EntitySchema


@dataclass(frozen=True, slots=True)
class RowIssue:
    row_number: int
    message: str
    column: str | None = None
    field_key: str | None = None
    value: str | None = None


@dataclass
class MappedRow:
    row_number: int
    values: dict[str, object] = field(default_factory=dict)

    def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)


def _column_for(mapping: dict[str, str], field_key: str) -> str | None:
    return next((source for source, target in mapping.items() if target == field_key), None)


def map_rows(
    numbered_rows,
    *,
    mapping: dict[str, str],
    schema: EntitySchema,
    options: CoercionOptions,
) -> tuple[list[MappedRow], list[RowIssue]]:
    mapped: list[MappedRow] = []
    issues: list[RowIssue] = []

    for row_number, raw in numbered_rows:
        values: dict[str, object] = {}
        row_failed = False

        for source, target in mapping.items():
            spec = schema.by_key(target)
            if spec is None:
                continue
            try:
                values[target] = coerce(
                    raw.get(source),
                    spec.type,
                    allowed=spec.enum_values,
                    options=options,
                )
            except CoercionError as exc:
                row_failed = True
                issues.append(
                    RowIssue(
                        row_number=row_number,
                        message=str(exc),
                        column=source,
                        field_key=target,
                        value=_short(raw.get(source)),
                    )
                )

        for key in schema.required_keys:
            if values.get(key) in (None, ""):
                row_failed = True
                issues.append(
                    RowIssue(
                        row_number=row_number,
                        message=f"«{schema.by_key(key).label}» es obligatorio y está vacío",
                        column=_column_for(mapping, key),
                        field_key=key,
                    )
                )

        if not row_failed:
            mapped.append(MappedRow(row_number=row_number, values=values))

    return mapped, issues


def deduplicate(
    rows: list[MappedRow], *, key_fields: tuple[str, ...], schema: EntitySchema
) -> tuple[list[MappedRow], list[RowIssue]]:
    """Fold rows that address the same record, keeping the last.

    A file listing the same SKU twice is nearly always a mistake, so the
    earlier occurrences are reported -- but the import still runs, because
    refusing the whole file over one repeated line helps nobody.
    """
    seen: dict[tuple, int] = {}
    issues: list[RowIssue] = []
    keep: dict[tuple, MappedRow] = {}

    for row in rows:
        identity = tuple(str(row.get(key) or "").strip().lower() for key in key_fields)
        if not any(identity):
            keep[(row.row_number,)] = row
            continue
        if identity in seen:
            labels = " + ".join(
                schema.by_key(key).label for key in key_fields if schema.by_key(key)
            )
            issues.append(
                RowIssue(
                    row_number=seen[identity],
                    message=(
                        f"Repetido en el archivo ({labels}: {' / '.join(identity)}); "
                        f"se usó la fila {row.row_number}"
                    ),
                    field_key=key_fields[0],
                )
            )
        seen[identity] = row.row_number
        keep[identity] = row

    ordered = sorted(keep.values(), key=lambda item: item.row_number)
    return ordered, issues


def _short(value: object, limit: int = 120) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
