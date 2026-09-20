import uuid
from typing import Protocol

from app.domain.customers.entities.customer import Customer
from app.domain.shared.document import DocumentType
from app.domain.shared.pagination import Page, PaginatedResult


class CustomerRepository(Protocol):
    async def get_by_id(self, company_id: uuid.UUID, customer_id: uuid.UUID) -> Customer | None: ...

    async def get_by_document(
        self, company_id: uuid.UUID, document_type: DocumentType, document_number: str
    ) -> Customer | None: ...

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResult[Customer]: ...

    async def add(self, customer: Customer) -> Customer: ...

    async def update(self, customer: Customer) -> Customer: ...
