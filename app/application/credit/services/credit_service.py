"""El único lugar donde cambia un saldo de fiado.

Ventas, abonos, reversiones y ajustes pasan todos por aquí, de modo que el
movimiento del libro y el saldo en caché se escriben juntos, bajo el mismo
bloqueo de fila y dentro de la transacción de quien llama. Nada más en el
código escribe `customer_balances`.

Es el mismo contrato que `StockService` tiene con el inventario, y por el mismo
motivo: si hubiera dos escritores, tarde o temprano uno olvidaría el libro.
"""

import uuid
from decimal import Decimal

from app.domain.credit.entities.account import (
    AccountEntry,
    CustomerBalance,
    EntryType,
)
from app.domain.credit.exceptions import CreditLimitExceededError
from app.domain.credit.repositories.credit_repository import CreditRepository


class CreditService:
    def __init__(self, credit: CreditRepository) -> None:
        self._credit = credit

    async def apply_entry(
        self,
        *,
        company_id: uuid.UUID,
        customer_id: uuid.UUID,
        amount: Decimal,
        entry_type: EntryType,
        reference_id: uuid.UUID | None = None,
        notes: str | None = None,
        created_by: uuid.UUID | None = None,
        credit_limit: Decimal | None = None,
    ) -> CustomerBalance:
        # Bloquear primero y decidir después: leer el saldo antes del bloqueo
        # dejaría que otra transacción invalidara la comprobación del cupo.
        balance = await self._credit.lock_balance(company_id, customer_id)

        if credit_limit is not None and amount > 0 and balance.would_exceed(amount, credit_limit):
            raise CreditLimitExceededError(
                "Esta venta supera el cupo de fiado del cliente",
                details={
                    "balance": str(balance.balance),
                    "credit_limit": str(credit_limit),
                    "sale_amount": str(amount),
                },
            )

        balance.apply(amount)
        saved = await self._credit.save_balance(balance)

        await self._credit.add_entry(
            AccountEntry(
                company_id=company_id,
                customer_id=customer_id,
                entry_type=entry_type,
                amount=amount,
                reference_id=reference_id,
                notes=notes,
                created_by=created_by,
            )
        )
        return saved
