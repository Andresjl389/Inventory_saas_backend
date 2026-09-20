"""Loading a whole company from one workbook.

The operator's path. A workbook with one sheet per entity is processed in
dependency order -- categories before products, products and warehouses before
stock -- inside a single savepoint, so a company is either onboarded or
untouched. That matters more here than for a single-entity import: a half-built
company is worse than an empty one, because the operator cannot tell by looking
which half is missing.
"""

from dataclasses import dataclass

from app.application.imports.services.loaders import loader_for
from app.application.imports.services.row_mapper import deduplicate, map_rows
from app.domain.imports.coercion import CoercionOptions
from app.domain.imports.entities.import_job import ImportStats
from app.domain.imports.exceptions import UnreadableFileError
from app.domain.imports.mapping import missing_required, suggest_mapping
from app.domain.imports.schemas import RECOMMENDED_ORDER, ImportEntity, schema_for
from app.domain.imports.table import SpreadsheetReader
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.tenants.tenant_context import TenantContext

MAX_ERRORS_PER_SHEET = 50


@dataclass
class SheetOutcome:
    entity: ImportEntity
    sheet: str | None
    status: str
    stats: dict[str, int]
    mapping: dict[str, str]
    unmapped_columns: list[str]
    missing_required: list[str]
    errors: list[dict]


def _match_sheet(sheets: dict, entity: ImportEntity) -> str | None:
    """Find a sheet for this entity by label or by entity name, case-folded.

    Users rename sheets ("Productos " with a trailing space, "PRODUCTOS"), so
    the match is loose rather than exact.
    """
    from app.domain.imports.mapping import normalise_header

    schema = schema_for(entity)
    wanted = {normalise_header(schema.label), normalise_header(entity.value)}
    for name in sheets:
        if normalise_header(name) in wanted:
            return name
    return None


class OnboardCompanyUseCase:
    def __init__(
        self, unit_of_work: UnitOfWork, repositories: dict, reader: SpreadsheetReader
    ) -> None:
        self._unit_of_work = unit_of_work
        self._repositories = repositories
        self._reader = reader

    async def execute(
        self, *, payload: bytes, tenant: TenantContext, dry_run: bool
    ) -> list[SheetOutcome]:
        sheets = self._reader.read_all_sheets(payload)
        if not sheets:
            raise UnreadableFileError("El archivo no tiene hojas legibles")

        outcomes: list[SheetOutcome] = []

        # One savepoint around every sheet: dependency order only helps if a
        # later failure takes the earlier sheets with it.
        async with self._unit_of_work.savepoint(commit=not dry_run):
            for entity in RECOMMENDED_ORDER:
                outcomes.append(await self._load_sheet(entity, sheets, tenant))

        return outcomes

    async def _load_sheet(
        self, entity: ImportEntity, sheets: dict, tenant: TenantContext
    ) -> SheetOutcome:
        schema = schema_for(entity)
        name = _match_sheet(sheets, entity)

        if name is None:
            return SheetOutcome(entity, None, "SKIPPED", ImportStats().as_dict(), {}, [], [], [])

        table = sheets[name]
        if not table.rows:
            return SheetOutcome(entity, name, "EMPTY", ImportStats().as_dict(), {}, [], [], [])

        suggestions = suggest_mapping(table.headers, schema)
        mapping = {item.source: item.target for item in suggestions if item.target}
        unmapped = [item.source for item in suggestions if not item.target]
        missing = missing_required(mapping, schema)

        if missing:
            return SheetOutcome(
                entity,
                name,
                "MISSING_COLUMNS",
                ImportStats(total_rows=len(table.rows)).as_dict(),
                mapping,
                unmapped,
                missing,
                [
                    {
                        "row_number": table.header_row,
                        "message": (f"Falta una columna para «{schema.by_key(key).label}»"),
                        "field_key": key,
                    }
                    for key in missing
                ],
            )

        rows, issues = map_rows(
            table.numbered(), mapping=mapping, schema=schema, options=CoercionOptions()
        )
        key_fields = (
            ("document_type", "document_number")
            if schema.key_field == "document_number"
            else (schema.key_field,)
        )
        rows, duplicates = deduplicate(rows, key_fields=key_fields, schema=schema)
        issues.extend(duplicates)

        result = await loader_for(entity, repositories=self._repositories).load(
            rows, tenant=tenant, options={}
        )
        issues.extend(result.issues)

        stats = result.stats
        stats.total_rows = len(table.rows)
        stats.errors = len(issues)

        return SheetOutcome(
            entity,
            name,
            "LOADED" if not issues else "LOADED_WITH_ERRORS",
            stats.as_dict(),
            mapping,
            unmapped,
            [],
            [
                {
                    "row_number": issue.row_number,
                    "column": issue.column,
                    "field_key": issue.field_key,
                    "value": issue.value,
                    "message": issue.message,
                }
                for issue in sorted(issues, key=lambda item: item.row_number)[:MAX_ERRORS_PER_SHEET]
            ],
        )


def outcomes_to_payload(outcomes: list[SheetOutcome]) -> dict:
    totals = ImportStats()
    for outcome in outcomes:
        totals.total_rows += outcome.stats.get("total_rows", 0)
        totals.created += outcome.stats.get("created", 0)
        totals.updated += outcome.stats.get("updated", 0)
        totals.skipped += outcome.stats.get("skipped", 0)
        totals.errors += outcome.stats.get("errors", 0)

    return {
        "totals": totals.as_dict(),
        "sheets": [
            {
                "entity": outcome.entity.value,
                "sheet": outcome.sheet,
                "status": outcome.status,
                "stats": outcome.stats,
                "mapping": outcome.mapping,
                "unmapped_columns": outcome.unmapped_columns,
                "missing_required": outcome.missing_required,
                "errors": outcome.errors,
            }
            for outcome in outcomes
        ],
    }
