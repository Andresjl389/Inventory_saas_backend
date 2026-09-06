import uuid

from app.application.tenants.dto.company import MembershipDTO
from app.domain.tenants.repositories.company_member_repository import CompanyMemberRepository
from app.domain.tenants.repositories.company_repository import CompanyRepository


class ListMyCompaniesUseCase:
    """Companies the caller can switch into. Drives the company picker in the UI."""

    def __init__(self, companies: CompanyRepository, members: CompanyMemberRepository) -> None:
        self._companies = companies
        self._members = members

    async def execute(self, user_id: uuid.UUID) -> list[MembershipDTO]:
        memberships = {m.company_id: m for m in await self._members.list_by_user(user_id)}
        companies = await self._companies.list_for_user(user_id)
        return [
            MembershipDTO(
                company_id=company.id,
                company_name=company.name,
                role=memberships[company.id].role,
                is_active=memberships[company.id].is_active,
            )
            for company in companies
            if company.id in memberships
        ]
