import uuid
from typing import Protocol

from app.domain.sales.entities.sale import Sale, SaleStatus
from app.domain.shared.pagination import Page, PaginatedResult


class SaleRepository(Protocol):
    async def get_by_id(self, company_id: uuid.UUID, sale_id: uuid.UUID) -> Sale | None:
        """Return the sale with its items loaded."""
        ...

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        status: SaleStatus | None = None,
        customer_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> PaginatedResult[Sale]: ...

    async def add(self, sale: Sale) -> Sale:
        """Persist the header and every item in one go."""
        ...

    async def update_header(self, sale: Sale) -> Sale:
        """Items are immutable once written; only the header changes."""
        ...
