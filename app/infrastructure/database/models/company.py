import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint, true
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.tenants.entities.company import CompanyStatus, DocumentType
from app.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_column,
)


class CompanyModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    document_type: Mapped[DocumentType | None] = mapped_column(
        enum_column(DocumentType, "document_type"), nullable=True
    )
    document_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[CompanyStatus] = mapped_column(
        enum_column(CompanyStatus, "company_status"),
        nullable=False,
        default=CompanyStatus.ACTIVE,
        server_default=CompanyStatus.ACTIVE.value,
    )

    __table_args__ = (UniqueConstraint("document_type", "document_number"),)


class CompanyMemberModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "company_members"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    __table_args__ = (
        UniqueConstraint("company_id", "user_id"),
        Index("ix_company_members_company_id", "company_id"),
        Index("ix_company_members_user_id", "user_id"),
        Index("ix_company_members_role_id", "role_id"),
    )
