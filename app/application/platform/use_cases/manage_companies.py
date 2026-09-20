"""Platform-admin company management.

Provisioning is the flow the operator actually uses: one call creates the
company, guarantees it has an owner who can log in, and puts it on a plan.
Everything happens in the request transaction, so a half-provisioned company
-- one nobody can reach -- cannot exist.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.application.audit.services.audit_service import AuditService
from app.application.platform.dto.admin import (
    AdminCompanyDTO,
    AdminCompanyPageDTO,
    AdminUserDTO,
    ListCompaniesQuery,
    ProvisionCompanyCommand,
    ProvisionedCompanyDTO,
    SubscriptionDTO,
    UpdateCompanyCommand,
)
from app.domain.audit.entities.audit_entry import AuditAction
from app.domain.authorization.permissions import SystemRole
from app.domain.authorization.repositories.role_repository import RoleRepository
from app.domain.billing.entities.plan import Subscription, SubscriptionStatus
from app.domain.billing.exceptions import PlanNotFoundError
from app.domain.billing.repositories.billing_repository import (
    PlanRepository,
    SubscriptionRepository,
)
from app.domain.identity.entities.user import User
from app.domain.identity.repositories.user_repository import UserRepository
from app.domain.identity.value_objects.email import Email
from app.domain.shared.pagination import Page
from app.domain.tenants.entities.company import Company, CompanyStatus
from app.domain.tenants.entities.company_member import CompanyMember
from app.domain.tenants.exceptions import CompanyNotFoundError
from app.domain.tenants.repositories.company_member_repository import CompanyMemberRepository
from app.domain.tenants.repositories.company_repository import CompanyRepository
from app.shared.exceptions import ValidationError
from app.shared.security import hash_password

DEFAULT_PLAN_CODE = "FREE"


class ProvisionCompanyUseCase:
    def __init__(
        self,
        companies: CompanyRepository,
        members: CompanyMemberRepository,
        users: UserRepository,
        roles: RoleRepository,
        plans: PlanRepository,
        subscriptions: SubscriptionRepository,
        audit: AuditService,
    ) -> None:
        self._companies = companies
        self._members = members
        self._users = users
        self._roles = roles
        self._plans = plans
        self._subscriptions = subscriptions
        self._audit = audit

    async def execute(
        self, command: ProvisionCompanyCommand, *, actor_id: uuid.UUID
    ) -> ProvisionedCompanyDTO:
        owner_email = Email(command.owner_email).value
        owner = await self._users.get_by_email(owner_email)
        owner_created = owner is None

        if owner is None:
            if not command.owner_password:
                raise ValidationError(
                    "owner_password is required when the owner has no account yet",
                    code="OWNER_PASSWORD_REQUIRED",
                )
            owner = await self._users.add(
                User(
                    email=owner_email,
                    password_hash=hash_password(command.owner_password),
                    first_name=(command.owner_first_name or owner_email.split("@")[0]).strip(),
                    last_name=(command.owner_last_name or "").strip() or "Owner",
                )
            )

        company = await self._companies.add(
            Company(
                name=command.name.strip(),
                legal_name=command.legal_name,
                document_type=command.document_type,
                document_number=command.document_number,
                email=str(command.email) if command.email else None,
                phone=command.phone,
            )
        )

        owner_role = await self._roles.get_by_code(SystemRole.OWNER.value, company_id=None)
        assert owner_role is not None, "the OWNER system role is seeded by migration 0008"
        await self._members.add(
            CompanyMember(
                company_id=company.id,
                user_id=owner.id,
                role_id=owner_role.id,
                role_code=owner_role.code,
            )
        )

        subscription_dto = await self._attach_plan(company.id, command.plan_code)

        await self._audit.record(
            AuditAction.COMPANY_CREATED,
            actor_user_id=actor_id,
            company_id=company.id,
            entity_type="company",
            entity_id=company.id,
            payload={
                "name": company.name,
                "owner_email": owner_email,
                "owner_created": owner_created,
                "plan": command.plan_code or DEFAULT_PLAN_CODE,
            },
        )

        return ProvisionedCompanyDTO(
            company=AdminCompanyDTO.model_validate(company, from_attributes=True),
            owner=AdminUserDTO.model_validate(owner, from_attributes=True),
            owner_created=owner_created,
            subscription=subscription_dto,
        )

    async def _attach_plan(
        self, company_id: uuid.UUID, plan_code: str | None
    ) -> SubscriptionDTO | None:
        plan = await self._plans.get_by_code(plan_code or DEFAULT_PLAN_CODE)
        if plan is None:
            if plan_code:
                raise PlanNotFoundError(f"No plan with code '{plan_code}'")
            # A deployment that deleted the seeded FREE plan simply gets a
            # company with no subscription rather than a failed provision.
            return None

        now = datetime.now(UTC)
        subscription = await self._subscriptions.add(
            Subscription(
                company_id=company_id,
                plan_id=plan.id,
                status=SubscriptionStatus.TRIALING,
                started_at=now,
                current_period_end=now + timedelta(days=30),
            )
        )
        return SubscriptionDTO.model_validate(subscription, from_attributes=True)


class ListCompaniesUseCase:
    def __init__(self, companies: CompanyRepository) -> None:
        self._companies = companies

    async def execute(self, query: ListCompaniesQuery) -> AdminCompanyPageDTO:
        result = await self._companies.list_all(
            page=Page(number=query.page, size=query.size),
            search=query.search,
            status=query.status,
        )
        return AdminCompanyPageDTO(
            items=[
                AdminCompanyDTO.model_validate(row, from_attributes=True) for row in result.items
            ],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class GetCompanyUseCase:
    def __init__(self, companies: CompanyRepository) -> None:
        self._companies = companies

    async def execute(self, company_id: uuid.UUID) -> AdminCompanyDTO:
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError()
        return AdminCompanyDTO.model_validate(company, from_attributes=True)


class UpdateCompanyUseCase:
    def __init__(self, companies: CompanyRepository, audit: AuditService) -> None:
        self._companies = companies
        self._audit = audit

    async def execute(
        self, company_id: uuid.UUID, command: UpdateCompanyCommand, *, actor_id: uuid.UUID
    ) -> AdminCompanyDTO:
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError()

        previous_status = company.status
        for field in ("name", "legal_name", "document_type", "document_number", "phone"):
            value = getattr(command, field)
            if value is not None:
                setattr(company, field, value)
        if command.email is not None:
            company.email = str(command.email)
        if command.status is not None:
            company.status = command.status
        company.touch()

        updated = await self._companies.update(company)

        action = AuditAction.COMPANY_UPDATED
        if command.status is not None and command.status is not previous_status:
            action = (
                AuditAction.COMPANY_ACTIVATED
                if command.status is CompanyStatus.ACTIVE
                else AuditAction.COMPANY_SUSPENDED
            )
        await self._audit.record(
            action,
            actor_user_id=actor_id,
            company_id=company_id,
            entity_type="company",
            entity_id=company_id,
            payload={"status": updated.status.value, "previous_status": previous_status.value},
        )
        return AdminCompanyDTO.model_validate(updated, from_attributes=True)
