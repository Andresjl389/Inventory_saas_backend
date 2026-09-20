import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.imports.entities.import_job import ImportJob, ImportRowError
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.imports import ImportErrorModel, ImportJobModel
from app.infrastructure.database.repositories.mappers import (
    import_error_to_domain,
    import_job_to_domain,
)


class SqlAlchemyImportJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID, job_id: uuid.UUID) -> ImportJob | None:
        stmt = select(ImportJobModel).where(
            ImportJobModel.id == job_id, ImportJobModel.company_id == company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return import_job_to_domain(model) if model else None

    async def list(self, company_id: uuid.UUID, *, page: Page) -> PaginatedResult[ImportJob]:
        total = (
            await self._session.execute(
                select(func.count())
                .select_from(ImportJobModel)
                .where(ImportJobModel.company_id == company_id)
            )
        ).scalar_one()

        stmt = (
            select(ImportJobModel)
            .where(ImportJobModel.company_id == company_id)
            .order_by(ImportJobModel.created_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[import_job_to_domain(row) for row in rows], total=total, page=page
        )

    async def add(self, job: ImportJob) -> ImportJob:
        model = ImportJobModel(
            id=job.id,
            company_id=job.company_id,
            entity=job.entity,
            file_id=job.file_id,
            filename=job.filename,
            status=job.status,
            mapping=job.mapping,
            options=job.options,
            detected_columns=job.detected_columns,
            stats=job.stats,
            created_by=job.created_by,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return import_job_to_domain(model)

    async def update(self, job: ImportJob) -> ImportJob:
        stmt = select(ImportJobModel).where(
            ImportJobModel.id == job.id, ImportJobModel.company_id == job.company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Import job {job.id} disappeared before update")
        model.status = job.status
        model.mapping = job.mapping
        model.options = job.options
        model.detected_columns = job.detected_columns
        model.stats = job.stats
        model.failure_reason = job.failure_reason
        await self._session.flush()
        return import_job_to_domain(model)

    async def replace_errors(
        self, company_id: uuid.UUID, job_id: uuid.UUID, errors: Sequence[ImportRowError]
    ) -> None:
        """Each validation run supersedes the previous one's errors, so a user
        fixing their file never sees stale problems."""
        await self._session.execute(
            delete(ImportErrorModel).where(
                ImportErrorModel.job_id == job_id,
                ImportErrorModel.company_id == company_id,
            )
        )
        for error in errors:
            self._session.add(
                ImportErrorModel(
                    id=error.id,
                    company_id=error.company_id,
                    job_id=error.job_id,
                    row_number=error.row_number,
                    column=error.column,
                    field_key=error.field_key,
                    value=error.value,
                    message=error.message,
                )
            )
        await self._session.flush()

    async def list_errors(
        self, company_id: uuid.UUID, job_id: uuid.UUID, *, page: Page
    ) -> PaginatedResult[ImportRowError]:
        filters = [ImportErrorModel.job_id == job_id, ImportErrorModel.company_id == company_id]

        total = (
            await self._session.execute(
                select(func.count()).select_from(ImportErrorModel).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(ImportErrorModel)
            .where(*filters)
            .order_by(ImportErrorModel.row_number, ImportErrorModel.created_at)
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[import_error_to_domain(row) for row in rows], total=total, page=page
        )
