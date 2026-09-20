import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, false
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PermissionModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Global catalogue, seeded from app.domain.authorization.permissions."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class RoleModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """company_id NULL marks a system role shared by every company."""

    __tablename__ = "roles"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    __table_args__ = (
        # NULL company_id would make a plain UNIQUE(company_id, code) useless
        # (every NULL is distinct), so the two cases get their own indexes.
        Index(
            "uq_roles_system_code",
            "code",
            unique=True,
            postgresql_where="company_id IS NULL",
        ),
        Index(
            "uq_roles_company_id_code",
            "company_id",
            "code",
            unique=True,
            postgresql_where="company_id IS NOT NULL",
        ),
    )


class RolePermissionModel(TimestampMixin, Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # The composite primary key already enforces uniqueness.
    __table_args__ = (Index("ix_role_permissions_permission_id", "permission_id"),)
