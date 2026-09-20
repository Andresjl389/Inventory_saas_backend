import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.imports.entities.import_job import ImportStatus
from app.domain.imports.schemas import ImportEntity
from app.infrastructure.database.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)


class ImportJobModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "import_jobs"

    entity: Mapped[ImportEntity] = mapped_column(
        enum_column(ImportEntity, "import_entity"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ImportStatus] = mapped_column(
        enum_column(ImportStatus, "import_status"),
        nullable=False,
        default=ImportStatus.ANALYZED,
        server_default=ImportStatus.ANALYZED.value,
    )
    # Source column header -> target field key, as confirmed by the user.
    mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    detected_columns: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_import_jobs_company_id_created_at", "company_id", "created_at"),
        Index("ix_import_jobs_company_id_status", "company_id", "status"),
    )


class ImportErrorModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Row-level problems, kept in a table rather than a JSON blob so a large
    file's errors can be paged through instead of truncated."""

    __tablename__ = "import_errors"

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False
    )
    # The row number the user sees in their spreadsheet, header included.
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_import_errors_job_id_row_number", "job_id", "row_number"),)
