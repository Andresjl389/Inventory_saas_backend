"""An import in progress.

The job is what makes the two-phase flow possible: analyse first, let a human
confirm the mapping, then load. It records what was uploaded, how the columns
were matched and what happened, so a failed load can be explained afterwards
rather than only while it runs.
"""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domain.imports.schemas import ImportEntity
from app.domain.shared.entities import TenantEntity


class ImportStatus(StrEnum):
    ANALYZED = "ANALYZED"  # columns read, mapping suggested
    VALIDATED = "VALIDATED"  # dry run finished; may still carry row errors
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class ImportStats:
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "total_rows": self.total_rows,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
        }


@dataclass(kw_only=True)
class ImportJob(TenantEntity):
    entity: ImportEntity
    file_id: uuid.UUID
    filename: str
    status: ImportStatus = ImportStatus.ANALYZED
    # source column header -> target field key. Empty until analysis fills it
    # with suggestions and the user confirms.
    mapping: dict[str, str] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    # What analysis found: headers, sample values, suggested targets.
    detected_columns: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=lambda: ImportStats().as_dict())
    created_by: uuid.UUID | None = None
    failure_reason: str | None = None

    @property
    def is_open(self) -> bool:
        """A job that can still be reconfigured and run."""
        return self.status in (ImportStatus.ANALYZED, ImportStatus.VALIDATED)

    def set_mapping(self, mapping: dict[str, str], options: dict[str, Any] | None = None) -> None:
        self.mapping = mapping
        if options is not None:
            self.options = options
        self.status = ImportStatus.ANALYZED
        self.touch()

    def record_validation(self, stats: ImportStats) -> None:
        self.stats = stats.as_dict()
        self.status = ImportStatus.VALIDATED
        self.touch()

    def record_completion(self, stats: ImportStats) -> None:
        self.stats = stats.as_dict()
        self.status = ImportStatus.COMPLETED
        self.touch()

    def fail(self, reason: str) -> None:
        self.failure_reason = reason
        self.status = ImportStatus.FAILED
        self.touch()

    def cancel(self) -> None:
        self.status = ImportStatus.CANCELLED
        self.touch()


@dataclass(kw_only=True)
class ImportRowError(TenantEntity):
    """One problem with one cell, addressed the way the user sees the file:
    by row number and column name.

    Deliberately not called ImportError: that name belongs to Python, and this
    module would be a confusing place to shadow it.
    """

    job_id: uuid.UUID
    row_number: int
    column: str | None = None
    field_key: str | None = None
    value: str | None = None
    message: str
