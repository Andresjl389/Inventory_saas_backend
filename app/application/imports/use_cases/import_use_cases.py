"""The import pipeline: analyse, map, dry run, load.

The two-phase shape is the point. Analysis reads the file and *proposes* a
mapping; nothing is guessed silently at load time. The dry run then executes
the real loader inside a savepoint and rolls it back, so what the user is shown
includes every database constraint rather than a second, weaker set of checks
that would eventually disagree with the first.
"""

import uuid

from app.application.files.dto.file import FileDTO
from app.application.imports.dto.imports import (
    PREVIEW_ROWS,
    DetectedColumnDTO,
    EntitySchemaDTO,
    FieldSpecDTO,
    ImportAnalysisDTO,
    ImportErrorDTO,
    ImportJobDTO,
    ImportPageDTO,
    ImportResultDTO,
    ListImportsQuery,
    MappingCommand,
    PreviewCellDTO,
    PreviewRowDTO,
)
from app.application.imports.services.loaders import loader_for
from app.application.imports.services.row_mapper import (
    RowIssue,
    deduplicate,
    map_rows,
)
from app.domain.imports.coercion import CoercionError, CoercionOptions, coerce
from app.domain.imports.entities.import_job import (
    ImportJob,
    ImportRowError,
    ImportStats,
)
from app.domain.imports.exceptions import (
    ImportJobNotFoundError,
    ImportNotOpenError,
    MissingRequiredColumnsError,
    UnknownTargetFieldError,
)
from app.domain.imports.mapping import missing_required, suggest_mapping
from app.domain.imports.repositories.import_repository import ImportJobRepository
from app.domain.imports.schemas import (
    RECOMMENDED_ORDER,
    EntitySchema,
    ImportEntity,
    schema_for,
)
from app.domain.imports.table import SpreadsheetReader, SpreadsheetTable
from app.domain.shared.pagination import Page
from app.domain.shared.unit_of_work import UnitOfWork
from app.domain.tenants.tenant_context import TenantContext

# Enough to see in the response; the rest are paged from /errors.
ERROR_PREVIEW = 20
MAX_STORED_ERRORS = 2_000


def _job_dto(job: ImportJob) -> ImportJobDTO:
    return ImportJobDTO.model_validate(job, from_attributes=True)


def _field_dtos(schema: EntitySchema) -> list[FieldSpecDTO]:
    return [
        FieldSpecDTO(
            key=spec.key,
            label=spec.label,
            type=spec.type.value,
            required=spec.required,
            help=spec.help,
            enum_values=list(spec.enum_values),
            example=spec.example,
        )
        for spec in schema.fields
    ]


def describe_schemas(url_prefix: str = "") -> list[EntitySchemaDTO]:
    """The catalogue the mapping screen and the template list are built from,
    in the order a company should import in."""
    return [
        EntitySchemaDTO(
            entity=entity,
            label=schema_for(entity).label,
            description=schema_for(entity).description,
            key_field=schema_for(entity).key_field,
            options=list(schema_for(entity).options),
            fields=_field_dtos(schema_for(entity)),
            template_url=f"{url_prefix}/imports/templates/{entity.value}",
        )
        for entity in RECOMMENDED_ORDER
    ]


def _preview(
    table: SpreadsheetTable, mapping: dict[str, str], schema: EntitySchema, options: CoercionOptions
) -> list[PreviewRowDTO]:
    """Raw value and coerced value side by side, which is what makes a wrong
    guess about separators or dates visible before anything is written."""
    rows: list[PreviewRowDTO] = []
    for row_number, raw in list(table.numbered())[:PREVIEW_ROWS]:
        cells: list[PreviewCellDTO] = []
        for source, target in mapping.items():
            spec = schema.by_key(target)
            if spec is None:
                continue
            original = raw.get(source)
            try:
                value = coerce(original, spec.type, allowed=spec.enum_values, options=options)
                cells.append(
                    PreviewCellDTO(
                        field_key=target,
                        raw=None if original is None else str(original),
                        value=None if value is None else str(value),
                    )
                )
            except CoercionError as exc:
                cells.append(
                    PreviewCellDTO(
                        field_key=target,
                        raw=None if original is None else str(original),
                        value=None,
                        error=str(exc),
                    )
                )
        rows.append(PreviewRowDTO(row_number=row_number, cells=cells))
    return rows


def _coercion_options(job: ImportJob) -> CoercionOptions:
    return CoercionOptions(
        decimal_separator=job.options.get("decimal_separator"),
        date_format=job.options.get("date_format"),
    )


class AnalyzeImportUseCase:
    """Read an uploaded file and propose how its columns map to our fields."""

    def __init__(self, jobs: ImportJobRepository, reader: SpreadsheetReader) -> None:
        self._jobs = jobs
        self._reader = reader

    async def execute(
        self,
        *,
        payload: bytes,
        stored_file: FileDTO,
        entity: ImportEntity,
        tenant: TenantContext,
    ) -> ImportAnalysisDTO:
        schema = schema_for(entity)
        table = self._reader.read(payload, stored_file.content_type, stored_file.filename)
        suggestions = suggest_mapping(table.headers, schema)

        mapping = {
            suggestion.source: suggestion.target for suggestion in suggestions if suggestion.target
        }
        detected = [
            {
                "source": suggestion.source,
                "suggested_target": suggestion.target,
                "confidence": suggestion.confidence,
                "reason": suggestion.reason,
                "needs_review": suggestion.needs_review,
                "samples": table.samples(suggestion.source),
            }
            for suggestion in suggestions
        ]

        job = await self._jobs.add(
            ImportJob(
                company_id=tenant.company_id,
                entity=entity,
                file_id=stored_file.id,
                filename=stored_file.filename,
                mapping=mapping,
                options={},
                detected_columns=detected,
                stats=ImportStats(total_rows=len(table.rows)).as_dict(),
                created_by=tenant.user_id,
            )
        )

        return ImportAnalysisDTO(
            job=_job_dto(job),
            columns=[DetectedColumnDTO(**column) for column in detected],
            target_fields=_field_dtos(schema),
            missing_required=missing_required(mapping, schema),
            total_rows=len(table.rows),
            preview=_preview(table, mapping, schema, CoercionOptions()),
        )


class UpdateMappingUseCase:
    """Accept the user's corrections to the proposed mapping."""

    def __init__(self, jobs: ImportJobRepository, reader: SpreadsheetReader) -> None:
        self._jobs = jobs
        self._reader = reader

    async def execute(
        self,
        job_id: uuid.UUID,
        command: MappingCommand,
        *,
        payload: bytes,
        content_type: str,
        tenant: TenantContext,
    ) -> ImportAnalysisDTO:
        job = await _require_open_job(self._jobs, job_id, tenant)
        schema = schema_for(job.entity)

        unknown = sorted(set(command.mapping.values()) - {spec.key for spec in schema.fields})
        if unknown:
            raise UnknownTargetFieldError(
                f"Unknown target fields for {schema.label}: {', '.join(unknown)}",
                details={"unknown": unknown, "valid": [spec.key for spec in schema.fields]},
            )

        options = dict(command.options)
        if command.decimal_separator:
            options["decimal_separator"] = command.decimal_separator
        if command.date_format:
            options["date_format"] = command.date_format

        job.set_mapping(command.mapping, options)
        job = await self._jobs.update(job)

        table = self._reader.read(payload, content_type, job.filename)
        return ImportAnalysisDTO(
            job=_job_dto(job),
            columns=[DetectedColumnDTO(**column) for column in job.detected_columns],
            target_fields=_field_dtos(schema),
            missing_required=missing_required(job.mapping, schema),
            total_rows=len(table.rows),
            preview=_preview(table, job.mapping, schema, _coercion_options(job)),
        )


class RunImportUseCase:
    """Execute an import, for real or as a dry run.

    Both paths run the same loader; a dry run simply rolls its savepoint back.
    That is what makes "validate" trustworthy: it is the actual load.
    """

    def __init__(
        self,
        jobs: ImportJobRepository,
        unit_of_work: UnitOfWork,
        repositories: dict,
        reader: SpreadsheetReader,
    ) -> None:
        self._jobs = jobs
        self._unit_of_work = unit_of_work
        self._repositories = repositories
        self._reader = reader

    async def execute(
        self,
        job_id: uuid.UUID,
        *,
        payload: bytes,
        content_type: str,
        dry_run: bool,
        tenant: TenantContext,
    ) -> ImportResultDTO:
        job = await _require_open_job(self._jobs, job_id, tenant)
        schema = schema_for(job.entity)

        missing = missing_required(job.mapping, schema)
        if missing:
            labels = [schema.by_key(key).label for key in missing]
            raise MissingRequiredColumnsError(
                f"Faltan columnas para: {', '.join(labels)}",
                details={"missing": missing},
            )

        table = self._reader.read(payload, content_type, job.filename)
        options = _coercion_options(job)
        rows, issues = map_rows(
            table.numbered(), mapping=job.mapping, schema=schema, options=options
        )

        key_fields = _key_fields(schema)
        rows, duplicate_issues = deduplicate(rows, key_fields=key_fields, schema=schema)
        issues.extend(duplicate_issues)

        loader = loader_for(job.entity, repositories=self._repositories)
        async with self._unit_of_work.savepoint(commit=not dry_run):
            result = await loader.load(rows, tenant=tenant, options=job.options)

        issues.extend(result.issues)
        stats = result.stats
        stats.total_rows = len(table.rows)
        stats.errors = len(issues)

        await self._store_issues(job, issues, tenant)

        if dry_run:
            job.record_validation(stats)
        else:
            job.record_completion(stats)
        job = await self._jobs.update(job)

        return ImportResultDTO(
            job=_job_dto(job),
            dry_run=dry_run,
            stats=stats.as_dict(),
            errors_preview=[
                ImportErrorDTO(
                    row_number=issue.row_number,
                    column=issue.column,
                    field_key=issue.field_key,
                    value=issue.value,
                    message=issue.message,
                )
                for issue in issues[:ERROR_PREVIEW]
            ],
        )

    async def _store_issues(
        self, job: ImportJob, issues: list[RowIssue], tenant: TenantContext
    ) -> None:
        ordered = sorted(issues, key=lambda issue: issue.row_number)[:MAX_STORED_ERRORS]
        await self._jobs.replace_errors(
            tenant.company_id,
            job.id,
            [
                ImportRowError(
                    company_id=tenant.company_id,
                    job_id=job.id,
                    row_number=issue.row_number,
                    column=issue.column,
                    field_key=issue.field_key,
                    value=issue.value,
                    message=issue.message,
                )
                for issue in ordered
            ],
        )


class ListImportsUseCase:
    def __init__(self, jobs: ImportJobRepository) -> None:
        self._jobs = jobs

    async def execute(self, query: ListImportsQuery, *, tenant: TenantContext) -> ImportPageDTO:
        result = await self._jobs.list(
            tenant.company_id, page=Page(number=query.page, size=query.size)
        )
        return ImportPageDTO(
            items=[_job_dto(row) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class GetImportUseCase:
    def __init__(self, jobs: ImportJobRepository) -> None:
        self._jobs = jobs

    async def execute(self, job_id: uuid.UUID, *, tenant: TenantContext) -> ImportJobDTO:
        job = await self._jobs.get_by_id(tenant.company_id, job_id)
        if job is None:
            raise ImportJobNotFoundError()
        return _job_dto(job)


class ListImportErrorsUseCase:
    def __init__(self, jobs: ImportJobRepository) -> None:
        self._jobs = jobs

    async def execute(self, job_id: uuid.UUID, *, page: Page, tenant: TenantContext):
        if await self._jobs.get_by_id(tenant.company_id, job_id) is None:
            raise ImportJobNotFoundError()
        return await self._jobs.list_errors(tenant.company_id, job_id, page=page)


class CancelImportUseCase:
    def __init__(self, jobs: ImportJobRepository) -> None:
        self._jobs = jobs

    async def execute(self, job_id: uuid.UUID, *, tenant: TenantContext) -> ImportJobDTO:
        job = await _require_open_job(self._jobs, job_id, tenant)
        job.cancel()
        return _job_dto(await self._jobs.update(job))


def _key_fields(schema: EntitySchema) -> tuple[str, ...]:
    """Customers and suppliers are identified by type + number together, so a
    NIT and a passport that share digits are not folded into one record."""
    if schema.key_field == "document_number":
        return ("document_type", "document_number")
    return (schema.key_field,)


async def _require_open_job(
    jobs: ImportJobRepository, job_id: uuid.UUID, tenant: TenantContext
) -> ImportJob:
    job = await jobs.get_by_id(tenant.company_id, job_id)
    if job is None:
        raise ImportJobNotFoundError()
    if not job.is_open:
        raise ImportNotOpenError(
            f"Esta importación ya está en estado {job.status.value}",
            details={"status": job.status.value},
        )
    return job
