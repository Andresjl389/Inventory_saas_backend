import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.files.entities.stored_file import FileOwnerType, StoredFile
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.file import FileModel
from app.infrastructure.database.repositories.mappers import stored_file_to_domain


class SqlAlchemyFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID, file_id: uuid.UUID) -> StoredFile | None:
        stmt = select(FileModel).where(FileModel.id == file_id, FileModel.company_id == company_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return stored_file_to_domain(model) if model else None

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        owner_type: FileOwnerType | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> PaginatedResult[StoredFile]:
        filters = [FileModel.company_id == company_id]
        if owner_type is not None:
            filters.append(FileModel.owner_type == owner_type)
        if owner_id is not None:
            filters.append(FileModel.owner_id == owner_id)

        total = (
            await self._session.execute(select(func.count()).select_from(FileModel).where(*filters))
        ).scalar_one()

        stmt = (
            select(FileModel)
            .where(*filters)
            .order_by(FileModel.created_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[stored_file_to_domain(row) for row in rows], total=total, page=page
        )

    async def add(self, file: StoredFile) -> StoredFile:
        model = FileModel(
            id=file.id,
            company_id=file.company_id,
            owner_type=file.owner_type,
            owner_id=file.owner_id,
            filename=file.filename,
            content_type=file.content_type,
            size_bytes=file.size_bytes,
            storage_key=file.storage_key,
            checksum=file.checksum,
            uploaded_by=file.uploaded_by,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return stored_file_to_domain(model)

    async def delete(self, company_id: uuid.UUID, file_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(FileModel).where(FileModel.id == file_id, FileModel.company_id == company_id)
        )

    async def all_storage_keys(self) -> set[str]:
        """Every key the database knows about, for the orphan sweep.

        Only complete with the platform flag raised; RLS narrows it otherwise,
        which would make the sweep delete other tenants' live blobs. The caller
        in `app.infrastructure.jobs` uses a platform session for exactly this.
        """
        return set((await self._session.execute(select(FileModel.storage_key))).scalars().all())
