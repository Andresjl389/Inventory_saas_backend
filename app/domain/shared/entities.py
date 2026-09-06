"""Base entities.

Domain entities are plain Python objects. They must not import FastAPI,
SQLAlchemy, Redis or any other infrastructure concern.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(kw_only=True)
class BaseEntity:
    id: uuid.UUID = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def __eq__(self, other: object) -> bool:
        """Entities are compared by identity, not by attribute values."""
        if not isinstance(other, BaseEntity):
            return NotImplemented
        return type(self) is type(other) and self.id == other.id

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.id))


@dataclass(kw_only=True)
class TenantEntity(BaseEntity):
    """Anything owned by exactly one company (tenant)."""

    company_id: uuid.UUID
