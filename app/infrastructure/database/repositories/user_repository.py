import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.entities.user import User
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
        model.last_login_at = user.last_login_at
        await self._session.flush()
        return user_to_domain(model)
