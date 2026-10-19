import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.domain.credit.entities.account import AccountEntry, CustomerBalance
from app.domain.shared.pagination import Page, PaginatedResult


@dataclass(frozen=True, slots=True)
class AccountSummary:
    """Una fila de la pantalla «cuentas claras»."""

    customer_id: uuid.UUID
    customer_name: str
    phone: str | None
    balance: Decimal
    credit_limit: Decimal
    last_movement_at: object | None


@dataclass(frozen=True, slots=True)
class CreditTotals:
    customers_with_debt: int
    total_receivable: Decimal


class CreditRepository(Protocol):
    async def lock_balance(self, company_id: uuid.UUID, customer_id: uuid.UUID) -> CustomerBalance:
        """Devuelve el saldo creándolo en cero si no existe, con la fila
        bloqueada hasta el final de la transacción.

        Es lo que impide que dos abonos simultáneos dejen el saldo mal, igual
        que con el stock.
        """
        ...

    async def get_balance(
        self, company_id: uuid.UUID, customer_id: uuid.UUID
    ) -> CustomerBalance | None: ...

    async def save_balance(self, balance: CustomerBalance) -> CustomerBalance: ...

    async def add_entry(self, entry: AccountEntry) -> AccountEntry: ...

    async def list_entries(
        self,
        company_id: uuid.UUID,
        customer_id: uuid.UUID,
        *,
        page: Page,
    ) -> PaginatedResult[AccountEntry]: ...

    async def list_accounts(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        search: str | None = None,
        only_with_balance: bool = True,
    ) -> PaginatedResult[AccountSummary]: ...

    async def totals(self, company_id: uuid.UUID) -> CreditTotals: ...
