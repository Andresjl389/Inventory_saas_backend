"""Plans and subscriptions, owned by the platform."""

import uuid
from datetime import UTC, datetime, timedelta

from app.application.audit.services.audit_service import AuditService
from app.application.platform.dto.admin import (
    AssignSubscriptionCommand,
    CreatePlanCommand,
    PlanDTO,
    SubscriptionDTO,
    UpdatePlanCommand,
)
from app.domain.audit.entities.audit_entry import AuditAction
from app.domain.billing.entities.plan import Plan, Subscription
from app.domain.billing.exceptions import (
    DuplicatePlanCodeError,
    PlanNotFoundError,
)
from app.domain.billing.repositories.billing_repository import (
    PlanRepository,
    SubscriptionRepository,
)
from app.domain.tenants.exceptions import CompanyNotFoundError
from app.domain.tenants.repositories.company_repository import CompanyRepository


class ListPlansUseCase:
    def __init__(self, plans: PlanRepository) -> None:
        self._plans = plans

    async def execute(self, *, is_active: bool | None = None) -> list[PlanDTO]:
        return [
            PlanDTO.model_validate(plan, from_attributes=True)
            for plan in await self._plans.list(is_active=is_active)
        ]


class CreatePlanUseCase:
    def __init__(self, plans: PlanRepository) -> None:
        self._plans = plans

    async def execute(self, command: CreatePlanCommand) -> PlanDTO:
        plan = Plan(
            code=command.code,
            name=command.name.strip(),
            description=command.description,
            price_monthly=command.price_monthly,
            max_users=command.max_users,
            max_products=command.max_products,
            max_warehouses=command.max_warehouses,
        )
        if await self._plans.get_by_code(plan.code) is not None:
            raise DuplicatePlanCodeError()
        return PlanDTO.model_validate(await self._plans.add(plan), from_attributes=True)


class UpdatePlanUseCase:
    def __init__(self, plans: PlanRepository) -> None:
        self._plans = plans

    async def execute(self, plan_id: uuid.UUID, command: UpdatePlanCommand) -> PlanDTO:
        plan = await self._plans.get_by_id(plan_id)
        if plan is None:
            raise PlanNotFoundError()

        for field in (
            "name",
            "description",
            "price_monthly",
            "max_users",
            "max_products",
            "max_warehouses",
            "is_active",
        ):
            value = getattr(command, field)
            if value is not None:
                setattr(plan, field, value)
        plan.touch()

        return PlanDTO.model_validate(await self._plans.update(plan), from_attributes=True)


class AssignSubscriptionUseCase:
    """Put a company on a plan, creating or replacing its subscription."""

    def __init__(
        self,
        companies: CompanyRepository,
        plans: PlanRepository,
        subscriptions: SubscriptionRepository,
        audit: AuditService,
    ) -> None:
        self._companies = companies
        self._plans = plans
        self._subscriptions = subscriptions
        self._audit = audit

    async def execute(
        self,
        company_id: uuid.UUID,
        command: AssignSubscriptionCommand,
        *,
        actor_id: uuid.UUID,
    ) -> SubscriptionDTO:
        if await self._companies.get_by_id(company_id) is None:
            raise CompanyNotFoundError()

        plan = await self._plans.get_by_code(command.plan_code)
        if plan is None:
            raise PlanNotFoundError(f"No plan with code '{command.plan_code}'")

        now = datetime.now(UTC)
        period_end = now + timedelta(days=command.period_days)
        existing = await self._subscriptions.get_for_company(company_id)

        if existing is None:
            subscription = await self._subscriptions.add(
                Subscription(
                    company_id=company_id,
                    plan_id=plan.id,
                    status=command.status,
                    started_at=now,
                    current_period_end=period_end,
                )
            )
        else:
            existing.plan_id = plan.id
            existing.status = command.status
            existing.started_at = existing.started_at or now
            existing.current_period_end = period_end
            existing.cancelled_at = None
            existing.touch()
            subscription = await self._subscriptions.update(existing)

        await self._audit.record(
            AuditAction.SUBSCRIPTION_CHANGED,
            actor_user_id=actor_id,
            company_id=company_id,
            entity_type="subscription",
            entity_id=subscription.id,
            payload={"plan": plan.code, "status": command.status.value},
        )
        return SubscriptionDTO.model_validate(subscription, from_attributes=True)


class GetSubscriptionUseCase:
    def __init__(self, subscriptions: SubscriptionRepository, plans: PlanRepository) -> None:
        self._subscriptions = subscriptions
        self._plans = plans

    async def execute(self, company_id: uuid.UUID) -> SubscriptionDTO | None:
        subscription = await self._subscriptions.get_for_company(company_id)
        if subscription is None:
            return None
        return SubscriptionDTO.model_validate(subscription, from_attributes=True)
