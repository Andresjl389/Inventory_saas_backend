"""Attachments: product images, invoices, imports and exports.

The bytes live outside PostgreSQL (BACKEND.md section 42). Today that is a
local folder; the endpoints, the table and everything above `FileStorage` stay
the same when it becomes an S3 bucket.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Request, UploadFile
from fastapi import status as http_status
from fastapi.responses import StreamingResponse

from app.application.files.dto.file import FileDTO, FilePageDTO, ListFilesQuery
from app.application.files.services.owner_check import OwnerCheck
from app.application.files.use_cases.file_use_cases import (
    DeleteFileUseCase,
    DownloadFileUseCase,
    GetFileUseCase,
    ListFilesUseCase,
    UploadFileUseCase,
)
from app.domain.files.entities.stored_file import FileOwnerType
from app.domain.files.exceptions import FileTooLargeError
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import (
    FileRepoDep,
    FileStorageDep,
    ProductRepoDep,
    PurchaseRepoDep,
    SaleRepoDep,
)
from app.presentation.api.dependencies.tenant import require_permission
from app.shared.config.settings import settings

router = APIRouter(prefix="/files", tags=["files"])

ReadDep = Annotated[TenantContext, Depends(require_permission("files.read"))]
WriteDep = Annotated[TenantContext, Depends(require_permission("files.write"))]

UPLOAD_CHUNK = 64 * 1024

# Images are safe to render in the browser; anything else is handed over as a
# download so it is never interpreted in the page's origin.
INLINE_PREFIXES = ("image/",)


async def _chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(UPLOAD_CHUNK):
        yield chunk


def _reject_oversized_body(request: Request) -> None:
    """Refuse an obviously too-large body before Starlette spools it to disk.

    Content-Length can lie, so this is only a shortcut; the real limit is
    enforced chunk by chunk while the upload streams past.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_upload_size_bytes:
        raise FileTooLargeError(
            f"Maximum upload size is {settings.max_upload_size_mb} MB",
            details={"max_bytes": settings.max_upload_size_bytes},
        )


@router.post("", response_model=FileDTO, status_code=http_status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    tenant: WriteDep,
    files: FileRepoDep,
    storage: FileStorageDep,
    products: ProductRepoDep,
    sales: SaleRepoDep,
    purchases: PurchaseRepoDep,
    file: Annotated[UploadFile, File(description="The file itself")],
    owner_type: Annotated[FileOwnerType, Form()] = FileOwnerType.COMPANY,
    owner_id: Annotated[uuid.UUID | None, Form()] = None,
) -> FileDTO:
    """Upload an attachment (multipart/form-data).

    A product image is `owner_type=PRODUCT` with the product's id. The stored
    path is generated server-side from the content type -- the filename you
    send is only ever echoed back on download.
    """
    _reject_oversized_body(request)

    use_case = UploadFileUseCase(files, storage, OwnerCheck(products, sales, purchases))
    return await use_case.execute(
        chunks=_chunks(file),
        filename=file.filename or "file",
        content_type=file.content_type or "",
        owner_type=owner_type,
        owner_id=owner_id,
        tenant=tenant,
        url_prefix=settings.api_v1_prefix,
    )


@router.get("", response_model=FilePageDTO)
async def list_files(
    tenant: ReadDep,
    files: FileRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    owner_type: FileOwnerType | None = None,
    owner_id: uuid.UUID | None = None,
) -> FilePageDTO:
    """List attachments. Pass `owner_type=PRODUCT&owner_id=...` for one
    product's images."""
    query = ListFilesQuery(page=page, size=size, owner_type=owner_type, owner_id=owner_id)
    return await ListFilesUseCase(files).execute(
        query, tenant=tenant, url_prefix=settings.api_v1_prefix
    )


@router.get("/{file_id}", response_model=FileDTO)
async def get_file(file_id: uuid.UUID, tenant: ReadDep, files: FileRepoDep) -> FileDTO:
    return await GetFileUseCase(files).execute(
        file_id, tenant=tenant, url_prefix=settings.api_v1_prefix
    )


@router.get("/{file_id}/content")
async def download_file(
    file_id: uuid.UUID, tenant: ReadDep, files: FileRepoDep, storage: FileStorageDep
) -> StreamingResponse:
    """Stream the bytes back.

    The lookup goes through the repository, so RLS decides whether the file
    exists at all: another tenant's id is a 404, never a download.
    """
    stored, stream = await DownloadFileUseCase(files, storage).execute(file_id, tenant=tenant)

    disposition = "inline" if stored.content_type.startswith(INLINE_PREFIXES) else "attachment"
    return StreamingResponse(
        stream,
        media_type=stored.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{stored.filename}"',
            "Content-Length": str(stored.size_bytes),
            # The content type is what we recorded, not what the browser
            # guesses from the bytes.
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.delete("/{file_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: uuid.UUID,
    tenant: WriteDep,
    files: FileRepoDep,
    storage: FileStorageDep,
    background: BackgroundTasks,
) -> None:
    """Delete an attachment.

    The row goes now; the blob is removed after the response, which is after
    the transaction commits. A rollback therefore cannot leave a row pointing
    at bytes that are already gone -- the worst case is an orphan blob, and the
    sweep reclaims those.
    """
    key = await DeleteFileUseCase(files).execute(file_id, tenant=tenant)
    background.add_task(storage.delete, key)
