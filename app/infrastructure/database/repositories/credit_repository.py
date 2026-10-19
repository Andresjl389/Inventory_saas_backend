import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.credit.entities.account import AccountEntry, CustomerBalance
from app.domain.credit.repositories.credit_repository import AccountSummary, CreditTotals
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.credit import AccountEntryModel, CustomerBalanceModel
from app.infrastructure.database.models.partner import CustomerModel
from app.infrastructure.database.repositories.mappers import (
    account_entry_to_domain,
    customer_balance_to_domain,
)


class SqlAlchemyCreditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_balance(self, company_id: uuid.UUID, customer_id: uuid.UUID) -> CustomerBalance:
        """Crea la fila si falta y la bloquea hasta el COMMIT.

        El INSERT ... ON CONFLICT DO NOTHING cierra la carrera de dos primeros
        movimientos simultáneos del mismo cliente; el SELECT ... FOR UPDATE
        serializa a todos los demás, que es lo que impide que dos abonos a la
        vez dejen el saldo mal.
        """
        upsert = (
            pg_insert(CustomerBalanceModel)
            .values(company_id=company_id, customer_id=customer_id, balance=Decimal("0"))
            .on_conflict_do_nothing(index_elements=["company_id", "customer_id"])
        )
        await self._session.execute(upsert)

        stmt = (
            select(CustomerBalanceModel)
            .where(
                CustomerBalanceModel.company_id == company_id,
                CustomerBalanceModel.customer_id == customer_id,
            )
            .with_for_update()
        )
        return customer_balance_to_domain((await self._session.execute(stmt)).scalar_one())

    async def get_balance(
        self, company_id: uuid.UUID, customer_id: uuid.UUID
    ) -> CustomerBalance | None:
        stmt = select(CustomerBalanceModel).where(
            CustomerBalanceModel.company_id == company_id,
            CustomerBalanceModel.customer_id == customer_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return customer_balance_to_domain(model) if model else None

    async def save_balance(self, balance: CustomerBalance) -> CustomerBalance:
        stmt = select(CustomerBalanceModel).where(
            CustomerBalanceModel.id == balance.id,
            CustomerBalanceModel.company_id == balance.company_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"El saldo {balance.id} desapareció antes de actualizarlo")
        model.balance = balance.balance
        await self._session.flush()
        return customer_balance_to_domain(model)

    async def add_entry(self, entry: AccountEntry) -> AccountEntry:
        model = AccountEntryModel(
            id=entry.id,
            company_id=entry.company_id,
            customer_id=entry.customer_id,
            entry_type=entry.entry_type,
            amount=entry.amount,
            reference_id=entry.reference_id,
            notes=entry.notes,
            created_by=entry.created_by,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return account_entry_to_domain(model)

    async def list_entries(
        self, company_id: uuid.UUID, customer_id: uuid.UUID, *, page: Page
    ) -> PaginatedResult[AccountEntry]:
        filters = [
            AccountEntryModel.company_id == company_id,
            AccountEntryModel.customer_id == customer_id,
        ]
        total = (
            await self._session.execute(
                select(func.count()).select_from(AccountEntryModel).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(AccountEntryModel)
            .where(*filters)
            .order_by(AccountEntryModel.created_at.desc(), AccountEntryModel.id.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[account_entry_to_domain(row) for row in rows], total=total, page=page
        )

    async def list_accounts(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        search: str | None = None,
        only_with_balance: bool = True,
    ) -> PaginatedResult[AccountSummary]:
        """La pantalla «cuentas claras»: quién debe, cuánto, y desde cuándo."""
        last_movement = (
            select(
                AccountEntryModel.customer_id,
                func.max(AccountEntryModel.created_at).label("last_at"),
            )
            .where(AccountEntryModel.company_id == company_id)
            .group_by(AccountEntryModel.customer_id)
            .subquery()
        )

        balance = func.coalesce(CustomerBalanceModel.balance, 0)
        filters = [CustomerModel.company_id == company_id]
        if only_with_balance:
            filters.append(balance != 0)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    CustomerModel.name.ilike(pattern),
                    CustomerModel.document_number.ilike(pattern),
                    CustomerModel.phone.ilike(pattern),
                )
            )

        base = (
            select(
                CustomerModel.id,
                CustomerModel.name,
                CustomerModel.phone,
                balance.label("balance"),
                CustomerModel.credit_limit,
                last_movement.c.last_at,
            )
            .select_from(CustomerModel)
            .outerjoin(
                CustomerBalanceModel,
                (CustomerBalanceModel.customer_id == CustomerModel.id)
                & (CustomerBalanceModel.company_id == company_id),
            )
            .outerjoin(last_movement, last_movement.c.customer_id == CustomerModel.id)
            .where(*filters)
        )

        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()

        rows = (
            await self._session.execute(
                base.order_by(balance.desc(), CustomerModel.name)
                .offset(page.offset)
                .limit(page.limit)
            )
        ).all()

        return PaginatedResult(
            items=[
                AccountSummary(
                    customer_id=row[0],
                    customer_name=row[1],
                    phone=row[2],
                    balance=row[3],
                    credit_limit=row[4],
                    last_movement_at=row[5],
                )
                for row in rows
            ],
            total=total,
            page=page,
        )

    async def totals(self, company_id: uuid.UUID) -> CreditTotals:
        row = (
            await self._session.execute(
                select(
                    func.count().filter(CustomerBalanceModel.balance > 0),
                    func.coalesce(
                        func.sum(CustomerBalanceModel.balance).filter(
                            CustomerBalanceModel.balance > 0
                        ),
                        0,
                    ),
                ).where(CustomerBalanceModel.company_id == company_id)
            )
        ).one()
        return CreditTotals(customers_with_debt=row[0], total_receivable=row[1])
