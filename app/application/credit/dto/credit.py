import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.credit.entities.account import EntryType, PaymentMethod
from app.domain.shared.pagination import MAX_PAGE_SIZE


class RegisterPaymentCommand(BaseModel):
    """Un abono. «Me abona 10 mil» es el 90% de los casos."""

    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    method: PaymentMethod = PaymentMethod.CASH
    notes: str | None = Field(default=None, max_length=500)


class AdjustAccountCommand(BaseModel):
    """Corrección manual: un perdón de deuda, un error del cuaderno viejo.

    Con signo: negativo baja la deuda, positivo la sube. Exige una nota porque
    un ajuste sin explicación es exactamente lo que vuelve turbias las cuentas.
    """

    amount: Decimal = Field(max_digits=18, decimal_places=4)
    notes: str = Field(min_length=3, max_length=500)


class AccountEntryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entry_type: EntryType
    amount: Decimal
    reference_id: uuid.UUID | None
    notes: str | None
    created_by: uuid.UUID | None
    created_at: datetime


class CustomerAccountDTO(BaseModel):
    """La cuenta de un cliente: cuánto debe y por qué."""

    customer_id: uuid.UUID
    customer_name: str
    phone: str | None
    # Con signo. Positivo: el cliente debe. Negativo: la tienda le debe.
    balance: Decimal
    # Las dos caras del saldo, ya separadas, para que la pantalla no tenga que
    # razonar sobre signos.
    owes: Decimal = Decimal("0")
    in_favor: Decimal = Decimal("0")
    credit_limit: Decimal
    available_credit: Decimal | None = None
    entries: list[AccountEntryDTO] = Field(default_factory=list)
    total_entries: int = 0
    page: int = 1
    size: int = 20
    pages: int = 0


class AccountSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: uuid.UUID
    customer_name: str
    phone: str | None
    balance: Decimal
    credit_limit: Decimal
    last_movement_at: datetime | None


class AccountPageDTO(BaseModel):
    items: list[AccountSummaryDTO]
    total: int
    page: int
    size: int
    pages: int


class CreditSummaryDTO(BaseModel):
    """El encabezado de «cuentas claras»: cuánto me deben en total."""

    customers_with_debt: int
    total_receivable: Decimal


class ListAccountsQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    search: str | None = None
    only_with_balance: bool = True
