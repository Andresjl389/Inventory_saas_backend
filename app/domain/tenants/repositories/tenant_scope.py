"""Port that lets a use case switch the *persistence* tenant scope.

Needed for exactly one situation: creating a company. The tenant context is
normally resolved before the use case runs, but a brand-new company has no
membership yet, so the use case has to declare "from now on this transaction
operates as company X" before writing the company and its owner row.

The infrastructure implementation maps this to PostgreSQL's transaction-local
`app.current_company_id` setting, which is what every RLS policy reads.
"""

import uuid
from typing import Protocol


class TenantScope(Protocol):
    async def enter(self, company_id: uuid.UUID) -> None: ...
