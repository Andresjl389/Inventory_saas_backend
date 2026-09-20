"""Uploading, listing, downloading and deleting attachments.

The order of the two writes in an upload is deliberate: the blob lands first,
then the metadata row. If the request fails in between, the result is an orphan
blob -- wasted bytes that the sweep reclaims -- rather than a row pointing at
nothing, which would be a broken download for a user.
"""

import hashlib
import uuid
from collections.abc import AsyncIterator

from app.application.files.dto.file import (
    FileDTO,
    FilePageDTO,
    ListFilesQuery,
)
from app.application.files.services.owner_check import OwnerCheck
from app.domain.files.entities.stored_file import FileOwnerType, StoredFile
from app.domain.files.exceptions import (
    EmptyFileError,
    FileNotFoundError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.domain.files.keys import build_key, safe_filename
from app.domain.files.repositories.file_repository import FileRepository
from app.domain.files.storage import FileStorage
from app.domain.shared.pagination import Page
from app.domain.tenants.tenant_context import TenantContext
from app.shared.config.settings import settings


def _to_dto(file: StoredFile, *, prefix: str) -> FileDTO:
    dto = FileDTO.model_validate(file, from_attributes=True)
    dto.download_url = f"{prefix}/files/{file.id}/content"
    return dto


class UploadFileUseCase:
    def __init__(
        self,
        files: FileRepository,
        storage: FileStorage,
        owner_check: OwnerCheck,
    ) -> None:
        self._files = files
        self._storage = storage
        self._owner_check = owner_check

    async def execute(
        self,
        *,
        chunks: AsyncIterator[bytes],
        filename: str,
        content_type: str,
        owner_type: FileOwnerType,
        owner_id: uuid.UUID | None,
        tenant: TenantContext,
        url_prefix: str = "",
    ) -> FileDTO:
        content_type = (content_type or "").split(";")[0].strip().lower()
        if content_type not in settings.allowed_upload_types:
            raise UnsupportedFileTypeError(
                f"{content_type or 'unknown'} is not an accepted file type",
                details={"allowed": sorted(settings.allowed_upload_types)},
            )

        await self._owner_check.assert_valid(owner_type, owner_id, tenant=tenant)

        key = build_key(
            company_id=tenant.company_id, owner_type=owner_type, content_type=content_type
        )
        digest = hashlib.sha256()
        size = await self._storage.save(key, self._metered(chunks, digest))

        if size == 0:
            await self._storage.delete(key)
            raise EmptyFileError()

        stored = await self._files.add(
            StoredFile(
                company_id=tenant.company_id,
                owner_type=owner_type,
                owner_id=owner_id,
                filename=safe_filename(filename),
                content_type=content_type,
                size_bytes=size,
                storage_key=key,
                checksum=digest.hexdigest(),
                uploaded_by=tenant.user_id,
            )
        )
        return _to_dto(stored, prefix=url_prefix)

    async def _metered(
        self, chunks: AsyncIterator[bytes], digest: "hashlib._Hash"
    ) -> AsyncIterator[bytes]:
        """Hash and count while the bytes stream past.

        The cap is enforced mid-stream rather than by reading the whole upload
        first, so a 5 GB body costs one chunk of memory and stops early. The
        storage adapter discards its staging file when this raises.
        """
        total = 0
        async for chunk in chunks:
            total += len(chunk)
            if total > settings.max_upload_size_bytes:
                raise FileTooLargeError(
                    f"Maximum upload size is {settings.max_upload_size_mb} MB",
                    details={"max_bytes": settings.max_upload_size_bytes},
                )
            digest.update(chunk)
            yield chunk


class ListFilesUseCase:
    def __init__(self, files: FileRepository) -> None:
        self._files = files

    async def execute(
        self, query: ListFilesQuery, *, tenant: TenantContext, url_prefix: str = ""
    ) -> FilePageDTO:
        result = await self._files.list(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            owner_type=query.owner_type,
            owner_id=query.owner_id,
        )
        return FilePageDTO(
            items=[_to_dto(row, prefix=url_prefix) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class GetFileUseCase:
    def __init__(self, files: FileRepository) -> None:
        self._files = files

    async def execute(
        self, file_id: uuid.UUID, *, tenant: TenantContext, url_prefix: str = ""
    ) -> FileDTO:
        file = await self._files.get_by_id(tenant.company_id, file_id)
        if file is None:
            raise FileNotFoundError()
        return _to_dto(file, prefix=url_prefix)


class DownloadFileUseCase:
    """Returns the metadata plus a stream of the bytes.

    The lookup goes through the repository, so RLS decides whether the file
    exists at all -- another tenant's id is a 404, never a download.
    """

    def __init__(self, files: FileRepository, storage: FileStorage) -> None:
        self._files = files
        self._storage = storage

    async def execute(
        self, file_id: uuid.UUID, *, tenant: TenantContext
    ) -> tuple[StoredFile, AsyncIterator[bytes]]:
        file = await self._files.get_by_id(tenant.company_id, file_id)
        if file is None:
            raise FileNotFoundError()
        return file, self._storage.open(file.storage_key)


class DeleteFileUseCase:
    """Removes the row and reports the key whose blob should go.

    The blob is deleted after the transaction commits (the router schedules it),
    so a rollback cannot leave a row pointing at bytes that are already gone.
    """

    def __init__(self, files: FileRepository) -> None:
        self._files = files

    async def execute(self, file_id: uuid.UUID, *, tenant: TenantContext) -> str:
        file = await self._files.get_by_id(tenant.company_id, file_id)
        if file is None:
            raise FileNotFoundError()
        await self._files.delete(tenant.company_id, file_id)
        return file.storage_key
