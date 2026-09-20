import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.imports.entities.import_job import ImportStatus
from app.domain.imports.schemas import ImportEntity
from app.domain.shared.pagination import MAX_PAGE_SIZE

PREVIEW_ROWS = 10


class FieldSpecDTO(BaseModel):
    """One target field, as the mapping screen needs to show it."""

    key: str
    label: str
    type: str
    required: bool
    help: str = ""
    enum_values: list[str] = Field(default_factory=list)
    example: str = ""


class EntitySchemaDTO(BaseModel):
    entity: ImportEntity
    label: str
    description: str
    key_field: str
    options: list[str] = Field(default_factory=list)
    fields: list[FieldSpecDTO]
    template_url: str = ""


class DetectedColumnDTO(BaseModel):
    """A column of the uploaded file and what we think it is."""

    source: str
    suggested_target: str | None
    confidence: float
    reason: str
    # True when the guess is plausible but not certain: show it selected and
    # highlighted rather than silently accepted.
    needs_review: bool = False
    samples: list[str] = Field(default_factory=list)


class PreviewCellDTO(BaseModel):
    field_key: str
    raw: str | None
    value: str | None
    error: str | None = None


class PreviewRowDTO(BaseModel):
    row_number: int
    cells: list[PreviewCellDTO]


class MappingCommand(BaseModel):
    """source column header -> target field key. Columns left out are ignored."""

    mapping: dict[str, str]
    options: dict[str, Any] = Field(default_factory=dict)
    # For files where 1.500 means one thousand five hundred (or one and a half)
    # and the importer should not have to guess.
    decimal_separator: str | None = Field(default=None, pattern=r"^[.,]$")
    date_format: str | None = Field(default=None, max_length=32)


class ImportJobDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    entity: ImportEntity
    file_id: uuid.UUID
    filename: str
    status: ImportStatus
    mapping: dict[str, str]
    options: dict[str, Any]
    stats: dict[str, int]
    failure_reason: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ImportAnalysisDTO(BaseModel):
    """What the mapping screen renders after an upload."""

    job: ImportJobDTO
    columns: list[DetectedColumnDTO]
    target_fields: list[FieldSpecDTO]
    missing_required: list[str]
    total_rows: int
    preview: list[PreviewRowDTO]


class ImportErrorDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    column: str | None
    field_key: str | None
    value: str | None
    message: str


class ImportErrorPageDTO(BaseModel):
    items: list[ImportErrorDTO]
    total: int
    page: int
    size: int
    pages: int


class ImportResultDTO(BaseModel):
    job: ImportJobDTO
    # A dry run reports exactly what a real run would do, then undoes it.
    dry_run: bool
    stats: dict[str, int]
    errors_preview: list[ImportErrorDTO]


class ListImportsQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)


class ImportPageDTO(BaseModel):
    items: list[ImportJobDTO]
    total: int
    page: int
    size: int
    pages: int
