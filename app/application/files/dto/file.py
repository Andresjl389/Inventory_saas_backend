import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.files.entities.stored_file import FileOwnerType
from app.domain.shared.pagination import MAX_PAGE_SIZE


class ListFilesQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    owner_type: FileOwnerType | None = None
    owner_id: uuid.UUID | None = None


class FileDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    owner_type: FileOwnerType
    owner_id: uuid.UUID | None
    filename: str
    content_type: str
    size_bytes: int
    checksum: str
    uploaded_by: uuid.UUID | None
    created_at: datetime
    # Where to fetch the bytes. The storage key is never exposed: it is an
    # implementation detail that changes when the backend does.
    download_url: str = ""


class FilePageDTO(BaseModel):
    items: list[FileDTO]
    total: int
    page: int
    size: int
    pages: int
