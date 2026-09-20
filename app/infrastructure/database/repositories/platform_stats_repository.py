from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenants.entities.company import CompanyStatus
from app.infrastructure.database.models.company import CompanyModel
from app.infrastructure.database.models.user import UserModel


class SqlAlchemyPlatformStatsRepository:
    """Counts for the operator console. Only meaningful with the platform-admin
    flag raised: the companies policy narrows the rows otherwise."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def counts(self) -> dict[str, int]:
        companies = (
            await self._session.execute(
                select(CompanyModel.status, func.count()).group_by(CompanyModel.status)
            )
        ).all()
        by_status = {status: count for status, count in companies}

        users_total, users_active, admins = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count().filter(UserModel.is_active.is_(True)),
                    func.count().filter(UserModel.is_superuser.is_(True)),
                ).select_from(UserModel)
            )
        ).one()

        return {
            "companies_total": sum(by_status.values()),
            "companies_active": by_status.get(CompanyStatus.ACTIVE, 0),
            "companies_suspended": by_status.get(CompanyStatus.SUSPENDED, 0),
            "users_total": users_total,
            "users_active": users_active,
            "platform_admins": admins,
        }
