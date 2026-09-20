"""Bulk import: upload a spreadsheet, confirm how its columns map, load it.

Two audiences, one engine. A company downloads the template, fills it and
uploads it -- its headers are the field labels, so the mapping resolves
automatically and the extra step is invisible. Anyone with a file that came out
of another system gets the same screen with the mapping exposed: their columns
on one side, our fields on the other, with a preview of the converted values.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi import status as http_status
from fastapi.responses import Response

from app.application.files.services.owner_check import OwnerCheck
from app.application.files.use_cases.file_use_cases import UploadFileUseCase
from app.application.imports.dto.imports import (
    EntitySchemaDTO,
    ImportAnalysisDTO,
    ImportErrorDTO,
    ImportErrorPageDTO,
    ImportJobDTO,
    ImportPageDTO,
    ImportResultDTO,
    ListImportsQuery,
    MappingCommand,
)
from app.application.imports.use_cases.import_use_cases import (
    AnalyzeImportUseCase,
    CancelImportUseCase,
    GetImportUseCase,
    ListImportErrorsUseCase,
    ListImportsUseCase,
    RunImportUseCase,
    UpdateMappingUseCase,
    describe_schemas,
)
from app.domain.files.entities.stored_file import FileOwnerType
from app.domain.imports.exceptions import ImportJobNotFoundError
from app.domain.imports.schemas import ImportEntity, schema_for
from app.domain.shared.pagination import MAX_PAGE_SIZE, Page
from app.domain.tenants.tenant_context import TenantContext
from app.infrastructure.imports.template import build_template
from app.presentation.api.dependencies.repositories import (
    FileRepoDep,
    FileStorageDep,
    ImportRepoDep,
    LoaderRepositoriesDep,
    ProductRepoDep,
    PurchaseRepoDep,
    SaleRepoDep,
    SpreadsheetReaderDep,
    UnitOfWorkDep,
)
from app.presentation.api.dependencies.tenant import require_permission
from app.shared.config.settings import settings

router = APIRouter(prefix="/imports", tags=["imports"])

ReadDep = Annotated[TenantContext, Depends(require_permission("imports.read"))]
RunDep = Annotated[TenantContext, Depends(require_permission("imports.run"))]

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
UPLOAD_CHUNK = 64 * 1024


async def _chunks(payload: bytes) -> AsyncIterator[bytes]:
    for start in range(0, len(payload), UPLOAD_CHUNK):
        yield payload[start : start + UPLOAD_CHUNK]


async def _stored_payload(job_id, tenant, jobs, files, storage) -> tuple[object, bytes]:
    """Re-read the uploaded file for a later step of the same job.

    Mapping, validating and loading all re-read the original rather than
    holding a parsed copy in memory between requests: the file is the record
    of what was imported, and re-reading keeps the three steps honest about
    working on the same bytes.
    """
    job = await jobs.get_by_id(tenant.company_id, job_id)
    if job is None:
        raise ImportJobNotFoundError()

    stored = await files.get_by_id(tenant.company_id, job.file_id)
    if stored is None:
        raise ImportJobNotFoundError("The uploaded file is no longer available")

    payload = b"".join([chunk async for chunk in storage.open(stored.storage_key)])
    return stored, payload


@router.get("/schemas", response_model=list[EntitySchemaDTO])
async def list_schemas(tenant: ReadDep) -> list[EntitySchemaDTO]:
    """Every importable entity with its fields, in the order to import them.

    This is what a mapping UI renders as the list of target fields -- the
    labels, which are required, what each one accepts.
    """
    return describe_schemas(settings.api_v1_prefix)


@router.get("/templates/{entity}")
async def download_template(entity: ImportEntity, tenant: ReadDep) -> Response:
    """The pre-formatted workbook: headers, an example row, and a second sheet
    documenting every field."""
    schema = schema_for(entity)
    filename = f"plantilla_{entity.value.lower()}.xlsx"
    return Response(
        content=build_template(schema),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=ImportAnalysisDTO, status_code=http_status.HTTP_201_CREATED)
async def analyze_import(
    request: Request,
    tenant: RunDep,
    jobs: ImportRepoDep,
    files: FileRepoDep,
    storage: FileStorageDep,
    products: ProductRepoDep,
    sales: SaleRepoDep,
    purchases: PurchaseRepoDep,
    reader: SpreadsheetReaderDep,
    file: Annotated[UploadFile, File(description=".xlsx or .csv")],
    entity: Annotated[ImportEntity, Form()],
) -> ImportAnalysisDTO:
    """Upload a file and get back the proposed mapping.

    Nothing is written to the company yet. The response carries the detected
    columns with sample values, the confidence of each suggestion, the list of
    target fields, and a preview of the converted values.
    """
    payload = await file.read()

    stored = await UploadFileUseCase(
        files, storage, OwnerCheck(products, sales, purchases)
    ).execute(
        chunks=_chunks(payload),
        filename=file.filename or "import.xlsx",
        content_type=file.content_type or XLSX_MEDIA_TYPE,
        owner_type=FileOwnerType.IMPORT,
        owner_id=None,
        tenant=tenant,
        url_prefix=settings.api_v1_prefix,
    )

    return await AnalyzeImportUseCase(jobs, reader).execute(
        payload=payload, stored_file=stored, entity=entity, tenant=tenant
    )


@router.patch("/{job_id}/mapping", response_model=ImportAnalysisDTO)
async def update_mapping(
    job_id: uuid.UUID,
    command: MappingCommand,
    tenant: RunDep,
    jobs: ImportRepoDep,
    files: FileRepoDep,
    storage: FileStorageDep,
    reader: SpreadsheetReaderDep,
) -> ImportAnalysisDTO:
    """Correct the mapping, and optionally pin how numbers and dates are read.

    Send `decimal_separator` when a file uses 1.500 for one thousand five
    hundred (or for one and a half) and the preview shows the wrong reading.
    """
    stored, payload = await _stored_payload(job_id, tenant, jobs, files, storage)
    return await UpdateMappingUseCase(jobs, reader).execute(
        job_id, command, payload=payload, content_type=stored.content_type, tenant=tenant
    )


@router.post("/{job_id}/validate", response_model=ImportResultDTO)
async def validate_import(
    job_id: uuid.UUID,
    tenant: RunDep,
    jobs: ImportRepoDep,
    files: FileRepoDep,
    storage: FileStorageDep,
    unit_of_work: UnitOfWorkDep,
    repositories: LoaderRepositoriesDep,
    reader: SpreadsheetReaderDep,
) -> ImportResultDTO:
    """Dry run: does the real load inside a savepoint and rolls it back.

    The counts and errors are therefore exactly what a real run would produce,
    database constraints included.
    """
    stored, payload = await _stored_payload(job_id, tenant, jobs, files, storage)
    return await RunImportUseCase(jobs, unit_of_work, repositories, reader).execute(
        job_id,
        payload=payload,
        content_type=stored.content_type,
        dry_run=True,
        tenant=tenant,
    )


@router.post("/{job_id}/run", response_model=ImportResultDTO)
async def run_import(
    job_id: uuid.UUID,
    tenant: RunDep,
    jobs: ImportRepoDep,
    files: FileRepoDep,
    storage: FileStorageDep,
    unit_of_work: UnitOfWorkDep,
    repositories: LoaderRepositoriesDep,
    reader: SpreadsheetReaderDep,
) -> ImportResultDTO:
    """Load the file. Rows with problems are reported and skipped; everything
    else is written in the request's transaction."""
    stored, payload = await _stored_payload(job_id, tenant, jobs, files, storage)
    return await RunImportUseCase(jobs, unit_of_work, repositories, reader).execute(
        job_id,
        payload=payload,
        content_type=stored.content_type,
        dry_run=False,
        tenant=tenant,
    )


@router.get("", response_model=ImportPageDTO)
async def list_imports(
    tenant: ReadDep,
    jobs: ImportRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> ImportPageDTO:
    return await ListImportsUseCase(jobs).execute(
        ListImportsQuery(page=page, size=size), tenant=tenant
    )


@router.get("/{job_id}", response_model=ImportJobDTO)
async def get_import(job_id: uuid.UUID, tenant: ReadDep, jobs: ImportRepoDep) -> ImportJobDTO:
    return await GetImportUseCase(jobs).execute(job_id, tenant=tenant)


@router.get("/{job_id}/errors", response_model=ImportErrorPageDTO)
async def list_import_errors(
    job_id: uuid.UUID,
    tenant: ReadDep,
    jobs: ImportRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> ImportErrorPageDTO:
    """Row-by-row problems, addressed by the row number in the user's file."""
    result = await ListImportErrorsUseCase(jobs).execute(
        job_id, page=Page(number=page, size=size), tenant=tenant
    )
    return ImportErrorPageDTO(
        items=[ImportErrorDTO.model_validate(row, from_attributes=True) for row in result.items],
        total=result.total,
        page=result.page.number,
        size=result.page.size,
        pages=result.pages,
    )


@router.post("/{job_id}/cancel", response_model=ImportJobDTO)
async def cancel_import(job_id: uuid.UUID, tenant: RunDep, jobs: ImportRepoDep) -> ImportJobDTO:
    return await CancelImportUseCase(jobs).execute(job_id, tenant=tenant)
