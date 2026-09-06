import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.tenants.entities.company import CompanyStatus, DocumentType
from app.domain.tenants.entities.company_member import CompanyRole
from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _enum(python_enum, name: str) -> Enum:
    """VARCHAR + CHECK instead of a native PG enum: adding a value later is a
    constraint change rather than an ALTER TYPE dance."""
    return Enum(
        python_enum,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class CompanyModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    document_type: Mapped[DocumentType | None] = mapped_column(
        _enum(DocumentType, "document_type"), nullable=True
    )
    document_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[CompanyStatus] = mapped_column(
        _enum(CompanyStatus, "company_status"),
        nullable=False,
        default=CompanyStatus.ACTIVE,
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
    role: Mapped[CompanyRole] = mapped_column(_enum(CompanyRole, "company_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (UniqueConstraint("company_id", "user_id"),)
