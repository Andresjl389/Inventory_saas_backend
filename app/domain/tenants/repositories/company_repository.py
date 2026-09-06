import uuid
from typing import Protocol

from app.domain.tenants.entities.company import Company


class CompanyRepository(Protocol):
    async def get_by_id(self, company_id: uuid.UUID) -> Company | None: ...

    async def add(self, company: Company) -> Company: ...

    async def update(self, company: Company) -> Company: ...

    async def list_for_user(self, user_id: uuid.UUID) -> list[Company]: ...
