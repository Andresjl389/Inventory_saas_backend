"""Port for user persistence. Implemented in the infrastructure layer."""

import uuid
from typing import Protocol

from app.domain.identity.entities.user import User


class UserRepository(Protocol):
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def exists_by_email(self, email: str) -> bool: ...

    async def add(self, user: User) -> User: ...

    async def update(self, user: User) -> User: ...
