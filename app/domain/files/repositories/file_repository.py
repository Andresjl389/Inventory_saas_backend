import uuid
from typing import Protocol

from app.domain.files.entities.stored_file import FileOwnerType, StoredFile
from app.domain.shared.pagination import Page, PaginatedResult


class FileRepository(Protocol):
    async def get_by_id(self, company_id: uuid.UUID, file_id: uuid.UUID) -> StoredFile | None: ...

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        owner_type: FileOwnerType | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> PaginatedResult[StoredFile]: ...

    async def add(self, file: StoredFile) -> StoredFile: ...

    async def delete(self, company_id: uuid.UUID, file_id: uuid.UUID) -> None: ...

    async def all_storage_keys(self) -> set[str]:
        """Every key the database knows about, for the orphan sweep."""
        ...
