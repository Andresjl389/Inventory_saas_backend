import uuid
from typing import Protocol

from app.domain.shared.document import DocumentType
from app.domain.shared.pagination import Page, PaginatedResult
from app.domain.suppliers.entities.supplier import Supplier


class SupplierRepository(Protocol):
    async def get_by_id(self, company_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier | None: ...

    async def get_by_document(
        self, company_id: uuid.UUID, document_type: DocumentType, document_number: str
    ) -> Supplier | None: ...

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResult[Supplier]: ...

    async def add(self, supplier: Supplier) -> Supplier: ...

    async def update(self, supplier: Supplier) -> Supplier: ...
