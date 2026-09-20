"""The shape a spreadsheet takes once it has been read.

Pure data: headers, rows and where the header sat in the file. It lives in the
domain so the application layer can talk about a parsed file without depending
on whatever library did the parsing.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

SAMPLE_SIZE = 5


@dataclass
class SpreadsheetTable:
    headers: list[str]
    rows: list[dict[str, object]] = field(default_factory=list)
    # Spreadsheet row number of the header, so errors point where the user looks.
    header_row: int = 1

    @property
    def first_data_row(self) -> int:
        return self.header_row + 1

    def samples(self, header: str, limit: int = SAMPLE_SIZE) -> list[str]:
        """A few real values from a column, for the mapping screen."""
        values = []
        for row in self.rows:
            value = row.get(header)
            if value not in (None, ""):
                values.append(str(value))
            if len(values) >= limit:
                break
        return values

    def numbered(self) -> Iterator[tuple[int, dict[str, object]]]:
        for offset, row in enumerate(self.rows):
            yield self.first_data_row + offset, row


class SpreadsheetReader(Protocol):
    """Port for turning uploaded bytes into tables."""

    def read(self, payload: bytes, content_type: str, filename: str = "") -> SpreadsheetTable: ...

    def read_all_sheets(self, payload: bytes) -> dict[str, SpreadsheetTable]:
        """Every sheet of a workbook, keyed by name, for onboarding files."""
        ...
