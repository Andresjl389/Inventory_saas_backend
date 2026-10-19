"""Consultar y mover la cuenta de fiado de un cliente."""

import uuid
from decimal import Decimal

from app.application.credit.dto.credit import (
    AccountEntryDTO,
    AccountPageDTO,
    AccountSummaryDTO,
    AdjustAccountCommand,
    CreditSummaryDTO,
    CustomerAccountDTO,
    ListAccountsQuery,
    RegisterPaymentCommand,
)
from app.application.credit.services.credit_service import CreditService
from app.domain.credit.entities.account import EntryType
from app.domain.credit.exceptions import (
    InvalidAccountEntryError,
    PaymentExceedsBalanceError,
)
from app.domain.credit.repositories.credit_repository import CreditRepository
from app.domain.customers.exceptions import CustomerNotFoundError
from app.domain.customers.repositories.customer_repository import CustomerRepository
from app.domain.shared.money import ZERO
from app.domain.shared.pagination import Page
from app.domain.tenants.tenant_context import TenantContext


class GetCustomerAccountUseCase:
    """Saldo e historial de un cliente: la pantalla de su cuenta."""

    def __init__(self, credit: CreditRepository, customers: CustomerRepository) -> None:
        self._credit = credit
        self._customers = customers

    async def execute(
        self, customer_id: uuid.UUID, *, page: Page, tenant: TenantContext
    ) -> CustomerAccountDTO:
        customer = await self._customers.get_by_id(tenant.company_id, customer_id)
        if customer is None:
            raise CustomerNotFoundError()

        balance = await self._credit.get_balance(tenant.company_id, customer_id)
        current = balance.balance if balance else ZERO
        entries = await self._credit.list_entries(tenant.company_id, customer_id, page=page)

        available = None
        if customer.credit_limit > 0:
            available = max(customer.credit_limit - current, ZERO)

        return CustomerAccountDTO(
            customer_id=customer.id,
            customer_name=customer.name,
            phone=customer.phone,
            balance=current,
            owes=max(current, ZERO),
            in_favor=max(-current, ZERO),
            credit_limit=customer.credit_limit,
            available_credit=available,
            entries=[
                AccountEntryDTO.model_validate(row, from_attributes=True) for row in entries.items
            ],
            total_entries=entries.total,
            page=entries.page.number,
            size=entries.page.size,
            pages=entries.pages,
        )


class RegisterPaymentUseCase:
    """Un abono. Baja el saldo y queda en el historial."""

    def __init__(
        self,
        credit: CreditRepository,
        customers: CustomerRepository,
        credit_service: CreditService,
    ) -> None:
        self._credit = credit
        self._customers = customers
        self._credit_service = credit_service

    async def execute(
        self, customer_id: uuid.UUID, command: RegisterPaymentCommand, *, tenant: TenantContext
    ) -> CustomerAccountDTO:
        customer = await self._customers.get_by_id(tenant.company_id, customer_id)
        if customer is None:
            raise CustomerNotFoundError()

        balance = await self._credit.get_balance(tenant.company_id, customer_id)
        current = balance.balance if balance else ZERO
        if command.amount > current:
            # Un abono mayor a la deuda casi siempre es un error de digitación
            # (50000 por 5000). Anticipos son otro producto, así que se avisa
            # en vez de inventarlos.
            raise PaymentExceedsBalanceError(
                "El abono es mayor que lo que debe el cliente",
                details={"balance": str(current), "amount": str(command.amount)},
            )

        await self._credit_service.apply_entry(
            company_id=tenant.company_id,
            customer_id=customer_id,
            amount=-command.amount,
            entry_type=EntryType.PAYMENT,
            notes=command.notes or f"Abono en {command.method.value.lower()}",
            created_by=tenant.user_id,
        )

        return await GetCustomerAccountUseCase(self._credit, self._customers).execute(
            customer_id, page=Page(number=1, size=20), tenant=tenant
        )


class AdjustAccountUseCase:
    """Corrección manual, siempre con explicación."""

    def __init__(
        self,
        credit: CreditRepository,
        customers: CustomerRepository,
        credit_service: CreditService,
    ) -> None:
        self._credit = credit
        self._customers = customers
        self._credit_service = credit_service

    async def execute(
        self, customer_id: uuid.UUID, command: AdjustAccountCommand, *, tenant: TenantContext
    ) -> CustomerAccountDTO:
        if await self._customers.get_by_id(tenant.company_id, customer_id) is None:
            raise CustomerNotFoundError()
        if command.amount == 0:
            raise InvalidAccountEntryError("Un ajuste de cero no cambia nada")

        await self._credit_service.apply_entry(
            company_id=tenant.company_id,
            customer_id=customer_id,
            amount=Decimal(command.amount),
            entry_type=EntryType.ADJUSTMENT,
            notes=command.notes,
            created_by=tenant.user_id,
        )

        return await GetCustomerAccountUseCase(self._credit, self._customers).execute(
            customer_id, page=Page(number=1, size=20), tenant=tenant
        )


class ListAccountsUseCase:
    """«Cuentas claras»: quién debe y cuánto, el que más debe primero."""

    def __init__(self, credit: CreditRepository) -> None:
        self._credit = credit

    async def execute(self, query: ListAccountsQuery, *, tenant: TenantContext) -> AccountPageDTO:
        result = await self._credit.list_accounts(
            tenant.company_id,
            page=Page(number=query.page, size=query.size),
            search=query.search,
            only_with_balance=query.only_with_balance,
        )
        return AccountPageDTO(
            items=[
                AccountSummaryDTO.model_validate(row, from_attributes=True) for row in result.items
            ],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class CreditSummaryUseCase:
    def __init__(self, credit: CreditRepository) -> None:
        self._credit = credit

    async def execute(self, *, tenant: TenantContext) -> CreditSummaryDTO:
        totals = await self._credit.totals(tenant.company_id)
        return CreditSummaryDTO(
            customers_with_debt=totals.customers_with_debt,
            total_receivable=totals.total_receivable,
        )
