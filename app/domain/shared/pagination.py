"""Pagination primitives shared by every repository."""

from dataclasses import dataclass

MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class Page:
    number: int = 1
    size: int = 20

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError("Page number starts at 1")
        if not 1 <= self.size <= MAX_PAGE_SIZE:
            raise ValueError(f"Page size must be between 1 and {MAX_PAGE_SIZE}")

    @property
    def offset(self) -> int:
        return (self.number - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


@dataclass(frozen=True, slots=True)
class PaginatedResult[T]:
    items: list[T]
    total: int
    page: Page

    @property
    def pages(self) -> int:
        return (self.total + self.page.size - 1) // self.page.size if self.total else 0
