import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.billing.entities.plan import Plan, Subscription
from app.infrastructure.database.models.platform import PlanModel, SubscriptionModel
from app.infrastructure.database.repositories.mappers import plan_to_domain, subscription_to_domain

_PLAN_FIELDS = (
    "code",
    "name",
    "description",
    "price_monthly",
    "max_users",
    "max_products",
    "max_warehouses",
    "is_active",
)


class SqlAlchemyPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, plan_id: uuid.UUID) -> Plan | None:
        model = await self._session.get(PlanModel, plan_id)
        return plan_to_domain(model) if model else None

    async def get_by_code(self, code: str) -> Plan | None:
        stmt = select(PlanModel).where(PlanModel.code == code.strip().upper())
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return plan_to_domain(model) if model else None

    async def list(self, *, is_active: bool | None = None) -> list[Plan]:
        stmt = select(PlanModel).order_by(PlanModel.price_monthly)
        if is_active is not None:
            stmt = stmt.where(PlanModel.is_active.is_(is_active))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [plan_to_domain(row) for row in rows]

    async def add(self, plan: Plan) -> Plan:
        model = PlanModel(id=plan.id, **{f: getattr(plan, f) for f in _PLAN_FIELDS})
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return plan_to_domain(model)

    async def update(self, plan: Plan) -> Plan:
        model = await self._session.get(PlanModel, plan.id)
        if model is None:
            raise LookupError(f"Plan {plan.id} disappeared before update")
        for field in _PLAN_FIELDS:
            setattr(model, field, getattr(plan, field))
        await self._session.flush()
        return plan_to_domain(model)


class SqlAlchemySubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_company(self, company_id: uuid.UUID) -> Subscription | None:
        stmt = select(SubscriptionModel).where(SubscriptionModel.company_id == company_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return subscription_to_domain(model) if model else None

    async def add(self, subscription: Subscription) -> Subscription:
        model = SubscriptionModel(
            id=subscription.id,
            company_id=subscription.company_id,
            plan_id=subscription.plan_id,
            status=subscription.status,
            started_at=subscription.started_at,
            current_period_end=subscription.current_period_end,
            cancelled_at=subscription.cancelled_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return subscription_to_domain(model)

    async def update(self, subscription: Subscription) -> Subscription:
        stmt = select(SubscriptionModel).where(SubscriptionModel.id == subscription.id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Subscription {subscription.id} disappeared before update")
        model.plan_id = subscription.plan_id
        model.status = subscription.status
        model.started_at = subscription.started_at
        model.current_period_end = subscription.current_period_end
        model.cancelled_at = subscription.cancelled_at
        await self._session.flush()
        return subscription_to_domain(model)
