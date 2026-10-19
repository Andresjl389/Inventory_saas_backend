"""El fiado: la cuenta corriente de un cliente.

Modelado igual que el inventario, y por la misma razón. El saldo no es un
número que alguien edita: es la suma de un libro append-only. Así "cuentas
claras" significa que cada peso que alguien debe se puede explicar con la venta
o el abono que lo movió, y no hay forma de que el saldo y su historia
discrepen.

    customer_balances.balance == SUM(customer_account_entries.amount)

El `amount` lleva signo: positivo aumenta la deuda (una venta fiada), negativo
la reduce (un abono). Guardar el signo en vez de una magnitud más un tipo es lo
que vuelve ese invariante una suma trivial de verificar.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.credit.exceptions import InvalidAccountEntryError
from app.domain.shared.entities import TenantEntity, utc_now
from app.domain.shared.money import ZERO, money


class EntryType(StrEnum):
    SALE = "SALE"  # una venta quedó fiada
    PAYMENT = "PAYMENT"  # el cliente abonó
    SALE_REVERSED = "SALE_REVERSED"  # se canceló o devolvió una venta fiada
    ADJUSTMENT = "ADJUSTMENT"  # corrección manual: un perdón, un error

    @property
    def direction(self) -> int:
        """+1 aumenta la deuda, -1 la reduce, 0 deja libre el signo."""
        return {
            EntryType.SALE: 1,
            EntryType.PAYMENT: -1,
            EntryType.SALE_REVERSED: -1,
            EntryType.ADJUSTMENT: 0,
        }[self]


class PaymentMethod(StrEnum):
    CASH = "CASH"
    TRANSFER = "TRANSFER"
    # No entró plata ahora: toda la venta quedó fiada.
    CREDIT = "CREDIT"

    @property
    def settles_immediately(self) -> bool:
        return self is not PaymentMethod.CREDIT


@dataclass(kw_only=True)
class AccountEntry(TenantEntity):
    customer_id: uuid.UUID
    entry_type: EntryType
    amount: Decimal
    reference_id: uuid.UUID | None = None
    notes: str | None = None
    created_by: uuid.UUID | None = None

    def __post_init__(self) -> None:
        self.amount = money(self.amount)
        if self.amount == 0:
            raise InvalidAccountEntryError("Un movimiento de cuenta no puede ser de cero")

        direction = self.entry_type.direction
        if direction and (self.amount > 0) != (direction > 0):
            esperado = "positivo" if direction > 0 else "negativo"
            raise InvalidAccountEntryError(
                f"Un movimiento {self.entry_type.value} debe ser {esperado}"
            )

    # El libro es inmutable: `updated_at` existe solo porque viene de la base.
    def touch(self) -> None:
        self.updated_at = self.created_at or utc_now()


@dataclass(kw_only=True)
class CustomerBalance(TenantEntity):
    """Caché del saldo, escrita en la misma transacción que el movimiento que
    la cambia, bajo el mismo bloqueo de fila."""

    customer_id: uuid.UUID
    balance: Decimal = ZERO

    def apply(self, delta: Decimal) -> None:
        self.balance = money(self.balance + delta)
        self.touch()

    @property
    def owes(self) -> bool:
        return self.balance > 0

    @property
    def in_favor(self) -> Decimal:
        """Saldo a favor del cliente: la tienda le debe.

        Pasa cuando se devuelve una venta que el cliente ya había abonado en
        parte. El sistema no puede saber si el tendero le entregó la plata o se
        la dejó para la próxima, así que lo registra y lo muestra; el tendero lo
        salda con un ajuste cuando corresponda.
        """
        return -self.balance if self.balance < 0 else ZERO

    def would_exceed(self, extra: Decimal, limit: Decimal) -> bool:
        """`limit = 0` significa sin tope, igual que en los planes."""
        return limit > 0 and (self.balance + extra) > limit
