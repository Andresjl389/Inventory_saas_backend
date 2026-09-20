import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.files.entities.stored_file import FileOwnerType
from app.infrastructure.database.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)


class FileModel(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Metadata for a blob. The bytes live in the FileStorage adapter.

    `owner_id` has no foreign key on purpose: it points at whichever table
    `owner_type` names, and a column cannot reference several tables. The
    application checks the owner exists before writing the row.
    """

    __tablename__ = "files"

    owner_type: Mapped[FileOwnerType] = mapped_column(
        enum_column(FileOwnerType, "file_owner_type"), nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_files_company_id_owner_type_owner_id", "company_id", "owner_type", "owner_id"),
        Index("ix_files_company_id_created_at", "company_id", "created_at"),
    )
