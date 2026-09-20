"""Platform-admin user management.

`users` is not a tenant table and carries no RLS, so these use cases are
protected by the API guard alone. They must never be reachable from a
tenant-scoped route.
"""

import uuid

from app.application.audit.services.audit_service import AuditService
from app.application.platform.dto.admin import (
    AdminUserDTO,
    AdminUserPageDTO,
    CreateUserCommand,
    ListUsersQuery,
    UpdateUserCommand,
)
from app.domain.audit.entities.audit_entry import AuditAction
from app.domain.identity.entities.user import User
from app.domain.identity.exceptions import EmailAlreadyRegisteredError, UserNotFoundError
from app.domain.identity.repositories.user_repository import UserRepository
from app.domain.identity.value_objects.email import Email
from app.domain.shared.pagination import Page
from app.shared.exceptions import BusinessRuleError
from app.shared.security import hash_password


class ListUsersUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, query: ListUsersQuery) -> AdminUserPageDTO:
        result = await self._users.list(
            page=Page(number=query.page, size=query.size),
            search=query.search,
            is_active=query.is_active,
            is_superuser=query.is_superuser,
        )
        return AdminUserPageDTO(
            items=[AdminUserDTO.model_validate(row, from_attributes=True) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class CreateUserUseCase:
    def __init__(self, users: UserRepository, audit: AuditService) -> None:
        self._users = users
        self._audit = audit

    async def execute(self, command: CreateUserCommand, *, actor_id: uuid.UUID) -> AdminUserDTO:
        email = Email(command.email).value
        if await self._users.exists_by_email(email):
            raise EmailAlreadyRegisteredError()

        user = await self._users.add(
            User(
                email=email,
                password_hash=hash_password(command.password),
                first_name=command.first_name.strip(),
                last_name=command.last_name.strip(),
                is_superuser=command.is_superuser,
            )
        )
        await self._audit.record(
            AuditAction.USER_CREATED,
            actor_user_id=actor_id,
            entity_type="user",
            entity_id=user.id,
            payload={"email": email, "is_superuser": command.is_superuser},
        )
        return AdminUserDTO.model_validate(user, from_attributes=True)


class UpdateUserUseCase:
    def __init__(self, users: UserRepository, audit: AuditService) -> None:
        self._users = users
        self._audit = audit

    async def execute(
        self, user_id: uuid.UUID, command: UpdateUserCommand, *, actor_id: uuid.UUID
    ) -> AdminUserDTO:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()

        if user_id == actor_id and command.is_superuser is False:
            # Removing your own last privilege locks the platform console.
            raise BusinessRuleError(
                "You cannot remove your own platform-admin rights",
                code="CANNOT_DEMOTE_SELF",
            )
        if user_id == actor_id and command.is_active is False:
            raise BusinessRuleError(
                "You cannot deactivate your own account", code="CANNOT_DEACTIVATE_SELF"
            )

        actions: list[AuditAction] = []
        if command.first_name is not None:
            user.first_name = command.first_name.strip()
        if command.last_name is not None:
            user.last_name = command.last_name.strip()
        if command.password is not None:
            user.change_password(hash_password(command.password))
            actions.append(AuditAction.USER_PASSWORD_RESET)
        if command.is_superuser is not None:
            user.is_superuser = command.is_superuser
        if command.is_active is not None:
            user.is_active = command.is_active
            if not command.is_active:
                actions.append(AuditAction.USER_DEACTIVATED)
        user.touch()

        updated = await self._users.update(user)

        for action in actions or [AuditAction.USER_CREATED]:
            if action is AuditAction.USER_CREATED:
                continue
            await self._audit.record(
                action,
                actor_user_id=actor_id,
                entity_type="user",
                entity_id=user_id,
                payload={"email": updated.email},
            )
        return AdminUserDTO.model_validate(updated, from_attributes=True)
