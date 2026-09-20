import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.entities.user import User
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.database.repositories.mappers import user_to_domain


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return user_to_domain(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email.strip().lower())
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return user_to_domain(model) if model else None

    async def exists_by_email(self, email: str) -> bool:
        stmt = select(UserModel.id).where(UserModel.email == email.strip().lower())
        return (await self._session.execute(stmt)).first() is not None

    async def add(self, user: User) -> User:
        model = UserModel(
            id=user.id,
            email=user.email,
            password_hash=user.password_hash,
            first_name=user.first_name,
            last_name=user.last_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return user_to_domain(model)

    async def update(self, user: User) -> User:
        model = await self._session.get(UserModel, user.id)
        if model is None:
            raise LookupError(f"User {user.id} disappeared before update")
        model.email = user.email
        model.password_hash = user.password_hash
        model.first_name = user.first_name
        model.last_name = user.last_name
        model.is_active = user.is_active
        model.is_superuser = user.is_superuser
        model.last_login_at = user.last_login_at
        await self._session.flush()
        return user_to_domain(model)

    async def list(
        self,
        *,
        page: Page,
        search: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
    ) -> PaginatedResult[User]:
        """`users` carries no RLS -- it is not tenant-owned -- so this is gated
        by the platform-admin API guard alone. It must never be reachable from
        a tenant-scoped route."""
        filters = []
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    UserModel.email.ilike(pattern),
                    UserModel.first_name.ilike(pattern),
                    UserModel.last_name.ilike(pattern),
                )
            )
        if is_active is not None:
            filters.append(UserModel.is_active.is_(is_active))
        if is_superuser is not None:
            filters.append(UserModel.is_superuser.is_(is_superuser))

        total = (
            await self._session.execute(select(func.count()).select_from(UserModel).where(*filters))
        ).scalar_one()

        stmt = (
            select(UserModel)
            .where(*filters)
            .order_by(UserModel.created_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(items=[user_to_domain(row) for row in rows], total=total, page=page)
