"""Supervision: what is actually going on inside each company.

Every metric is read inside that company's own tenant scope, because the
business tables have no platform-admin escape. The list endpoint therefore
walks the companies on the current page one at a time -- the single place in
the system where an operator request touches more than one company, and it
does so sequentially, capped by the page size, never in one query.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.application.platform.dto.admin import (
    AdminCompanyDTO,
    CompanyMetricsDTO,
    CompanyOverviewDTO,
    CompanyRowDTO,
    CompanySupervisionPageDTO,
    ListCompaniesQuery,
    PlanDTO,
    PlanUsageDTO,
    SubscriptionDTO,
)
from app.domain.billing.entities.plan import UNLIMITED
from app.domain.billing.repositories.billing_repository import (
    PlanRepository,
    SubscriptionRepository,
)
from app.domain.shared.pagination import Page
from app.domain.tenants.exceptions import CompanyNotFoundError
from app.domain.tenants.repositories.company_repository import CompanyRepository

SALES_WINDOW_DAYS = 30


def _usage(metrics: CompanyMetricsDTO, plan: PlanDTO | None) -> list[PlanUsageDTO]:
    if plan is None:
        return []
    pairs = (
        ("users", metrics.active_members, plan.max_users),
        ("products", metrics.active_products, plan.max_products),
        ("warehouses", metrics.warehouses, plan.max_warehouses),
    )
    return [
        PlanUsageDTO(
            resource=resource,
            used=used,
            limit=limit,
            over_limit=limit != UNLIMITED and used > limit,
        )
        for resource, used, limit in pairs
    ]


class GetCompanyOverviewUseCase:
    """One company in detail: who is in it, what it holds, how it is doing
    against its plan."""

    def __init__(
        self,
        companies: CompanyRepository,
        overview,
        subscriptions: SubscriptionRepository,
        plans: PlanRepository,
    ) -> None:
        self._companies = companies
        self._overview = overview
        self._subscriptions = subscriptions
        self._plans = plans

    async def execute(
        self, company_id: uuid.UUID, *, window_days: int = SALES_WINDOW_DAYS
    ) -> CompanyOverviewDTO:
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError()

        since = datetime.now(UTC) - timedelta(days=window_days)
        metrics = CompanyMetricsDTO(**await self._overview.counters(company_id, since=since))

        subscription = await self._subscriptions.get_for_company(company_id)
        plan = await self._plans.get_by_id(subscription.plan_id) if subscription else None
        plan_dto = PlanDTO.model_validate(plan, from_attributes=True) if plan else None

        days_since = None
        if metrics.last_sale_at is not None:
            days_since = (datetime.now(UTC) - metrics.last_sale_at).days

        return CompanyOverviewDTO(
            company=AdminCompanyDTO.model_validate(company, from_attributes=True),
            subscription=(
                SubscriptionDTO.model_validate(subscription, from_attributes=True)
                if subscription
                else None
            ),
            plan=plan_dto,
            metrics=metrics,
            usage=_usage(metrics, plan_dto),
            days_since_last_sale=days_since,
        )


class SuperviseCompaniesUseCase:
    """The supervision table: a page of companies with live numbers.

    `with_metrics=False` is the cheap path and stays the default: the metrics
    cost a handful of queries per company, which is fine for a page of twenty
    and would not be for a thousand.
    """

    def __init__(
        self,
        companies: CompanyRepository,
        overview,
        subscriptions: SubscriptionRepository,
        plans: PlanRepository,
        enter_company,
    ) -> None:
        self._companies = companies
        self._overview = overview
        self._subscriptions = subscriptions
        self._plans = plans
        self._enter_company = enter_company

    async def execute(
        self, query: ListCompaniesQuery, *, with_metrics: bool
    ) -> CompanySupervisionPageDTO:
        result = await self._companies.list_all(
            page=Page(number=query.page, size=query.size),
            search=query.search,
            status=query.status,
        )

        since = datetime.now(UTC) - timedelta(days=SALES_WINDOW_DAYS)
        plans = {plan.id: plan for plan in await self._plans.list()}
        rows: list[CompanyRowDTO] = []

        for company in result.items:
            subscription = await self._subscriptions.get_for_company(company.id)
            plan = plans.get(subscription.plan_id) if subscription else None

            metrics = None
            if with_metrics:
                # Enter this company before reading its business tables; the
                # scope is replaced on each pass, never widened.
                await self._enter_company(company.id)
                metrics = CompanyMetricsDTO(
                    **await self._overview.counters(company.id, since=since)
                )

            rows.append(
                CompanyRowDTO(
                    company=AdminCompanyDTO.model_validate(company, from_attributes=True),
                    plan_code=plan.code if plan else None,
                    subscription_status=subscription.status if subscription else None,
                    metrics=metrics,
                )
            )

        return CompanySupervisionPageDTO(
            items=rows,
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )
