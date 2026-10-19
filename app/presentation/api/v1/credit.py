"""Fiado: la cuenta corriente de cada cliente.

Lo que el cuaderno hacía mal —un número que alguien tacha y vuelve a escribir—
aquí es un libro append-only: cada peso que alguien debe se explica con la
venta o el abono que lo movió. Por eso el saldo nunca se escribe directamente,
solo se deriva.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.credit.dto.credit import (
    AccountPageDTO,
    AdjustAccountCommand,
    CreditSummaryDTO,
    CustomerAccountDTO,
    ListAccountsQuery,
    RegisterPaymentCommand,
)
from app.application.credit.use_cases.credit_use_cases import (
    AdjustAccountUseCase,
    CreditSummaryUseCase,
    GetCustomerAccountUseCase,
    ListAccountsUseCase,
    RegisterPaymentUseCase,
)
from app.domain.shared.pagination import MAX_PAGE_SIZE, Page
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import (
    CreditRepoDep,
    CreditServiceDep,
    CustomerRepoDep,
)
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/credit", tags=["fiado"])

ReadDep = Annotated[TenantContext, Depends(require_permission("credit.read"))]
ManageDep = Annotated[TenantContext, Depends(require_permission("credit.manage"))]


@router.get("/summary", response_model=CreditSummaryDTO)
async def credit_summary(tenant: ReadDep, credit: CreditRepoDep) -> CreditSummaryDTO:
    """Cuánto me deben en total y cuántos clientes deben. El encabezado de la
    pantalla de cuentas."""
    return await CreditSummaryUseCase(credit).execute(tenant=tenant)


@router.get("/accounts", response_model=AccountPageDTO)
async def list_accounts(
    tenant: ReadDep,
    credit: CreditRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    only_with_balance: bool = True,
) -> AccountPageDTO:
    """«Cuentas claras»: quién debe y cuánto, el que más debe primero.

    Con `only_with_balance=false` incluye a los clientes al día, que es lo que
    necesitas para elegir a quién fiarle.
    """
    query = ListAccountsQuery(
        page=page, size=size, search=search, only_with_balance=only_with_balance
    )
    return await ListAccountsUseCase(credit).execute(query, tenant=tenant)


@router.get("/accounts/{customer_id}", response_model=CustomerAccountDTO)
async def customer_account(
    customer_id: uuid.UUID,
    tenant: ReadDep,
    credit: CreditRepoDep,
    customers: CustomerRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> CustomerAccountDTO:
    """El saldo de un cliente y cada movimiento que lo formó."""
    return await GetCustomerAccountUseCase(credit, customers).execute(
        customer_id, page=Page(number=page, size=size), tenant=tenant
    )


@router.post("/accounts/{customer_id}/payments", response_model=CustomerAccountDTO)
async def register_payment(
    customer_id: uuid.UUID,
    command: RegisterPaymentCommand,
    tenant: ManageDep,
    credit: CreditRepoDep,
    customers: CustomerRepoDep,
    credit_service: CreditServiceDep,
) -> CustomerAccountDTO:
    """Registrar un abono. Devuelve la cuenta ya actualizada, que es lo que la
    pantalla necesita mostrar enseguida."""
    return await RegisterPaymentUseCase(credit, customers, credit_service).execute(
        customer_id, command, tenant=tenant
    )


@router.post("/accounts/{customer_id}/adjustments", response_model=CustomerAccountDTO)
async def adjust_account(
    customer_id: uuid.UUID,
    command: AdjustAccountCommand,
    tenant: ManageDep,
    credit: CreditRepoDep,
    customers: CustomerRepoDep,
    credit_service: CreditServiceDep,
) -> CustomerAccountDTO:
    """Corrección manual: un perdón de deuda, un error del cuaderno viejo.

    El monto va con signo y la nota es obligatoria: un ajuste sin explicación
    es justo lo que vuelve turbias las cuentas.
    """
    return await AdjustAccountUseCase(credit, customers, credit_service).execute(
        customer_id, command, tenant=tenant
    )
