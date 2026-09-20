import uuid
from collections.abc import Sequence
from typing import Protocol

from app.domain.imports.entities.import_job import ImportJob, ImportRowError
from app.domain.shared.pagination import Page, PaginatedResult


class ImportJobRepository(Protocol):
    async def get_by_id(self, company_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob | None: ...

    async def list(self, company_id: uuid.UUID, *, page: Page) -> PaginatedResult[ImportJob]: ...

    async def add(self, job: ImportJob) -> ImportJob: ...

    async def update(self, job: ImportJob) -> ImportJob: ...

    async def replace_errors(
        self, company_id: uuid.UUID, job_id: uuid.UUID, errors: Sequence[ImportRowError]
    ) -> None:
        """Each validation run supersedes the previous one's errors."""
        ...

    async def list_errors(
        self, company_id: uuid.UUID, job_id: uuid.UUID, *, page: Page
    ) -> PaginatedResult[ImportRowError]: ...
