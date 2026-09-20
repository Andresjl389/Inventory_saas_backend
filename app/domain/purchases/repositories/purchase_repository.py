import uuid
from typing import Protocol

from app.domain.purchases.entities.purchase import Purchase, PurchaseStatus
from app.domain.shared.pagination import Page, PaginatedResult


class PurchaseRepository(Protocol):
    async def get_by_id(self, company_id: uuid.UUID, purchase_id: uuid.UUID) -> Purchase | None: ...

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        status: PurchaseStatus | None = None,
        supplier_id: uuid.UUID | None = None,
        warehouse_id: uuid.UUID | None = None,
    ) -> PaginatedResult[Purchase]: ...

    async def add(self, purchase: Purchase) -> Purchase: ...

    async def update_header(self, purchase: Purchase) -> Purchase: ...
