import uuid
from typing import Protocol

from app.domain.products.entities.product import Product
from app.domain.shared.pagination import Page, PaginatedResult


class ProductRepository(Protocol):
    """All methods are already tenant-scoped by the caller's TenantContext and,
    as a last barrier, by PostgreSQL RLS."""

    async def get_by_id(self, company_id: uuid.UUID, product_id: uuid.UUID) -> Product | None: ...

    async def get_by_sku(self, company_id: uuid.UUID, sku: str) -> Product | None: ...

    async def get_by_barcode(self, company_id: uuid.UUID, barcode: str) -> Product | None: ...

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        search: str | None = None,
        category_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResult[Product]: ...

    async def add(self, product: Product) -> Product: ...

    async def update(self, product: Product) -> Product: ...
