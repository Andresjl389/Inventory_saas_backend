import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.application.authorization.dto.role import (
    CreateRoleCommand,
    PermissionDTO,
    RoleDTO,
    UpdateRoleCommand,
)
from app.application.authorization.use_cases.role_use_cases import (
    CreateRoleUseCase,
    DeleteRoleUseCase,
    ListPermissionsUseCase,
    ListRolesUseCase,
    UpdateRoleUseCase,
)
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import PermissionRepoDep, RoleRepoDep
from app.presentation.api.dependencies.tenant import require_permission

router = APIRouter(prefix="/roles", tags=["roles"])

ReadDep = Annotated[TenantContext, Depends(require_permission("roles.read"))]
ManageDep = Annotated[TenantContext, Depends(require_permission("roles.manage"))]


@router.get("", response_model=list[RoleDTO])
async def list_roles(tenant: ReadDep, roles: RoleRepoDep) -> list[RoleDTO]:
    """The four built-in roles plus any this company defined."""
    return await ListRolesUseCase(roles).execute(tenant=tenant)


@router.get("/permissions", response_model=list[PermissionDTO])
async def list_permissions(tenant: ReadDep, permissions: PermissionRepoDep) -> list[PermissionDTO]:
    """The catalogue a custom role can draw from."""
    return await ListPermissionsUseCase(permissions).execute()


@router.post("", response_model=RoleDTO, status_code=status.HTTP_201_CREATED)
async def create_role(command: CreateRoleCommand, tenant: ManageDep, roles: RoleRepoDep) -> RoleDTO:
    return await CreateRoleUseCase(roles).execute(command, tenant=tenant)


@router.patch("/{role_id}", response_model=RoleDTO)
async def update_role(
    role_id: uuid.UUID,
    command: UpdateRoleCommand,
    tenant: ManageDep,
    roles: RoleRepoDep,
) -> RoleDTO:
    """Built-in roles are shared by every tenant and cannot be edited here."""
    return await UpdateRoleUseCase(roles).execute(role_id, command, tenant=tenant)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: uuid.UUID, tenant: ManageDep, roles: RoleRepoDep) -> None:
    await DeleteRoleUseCase(roles).execute(role_id, tenant=tenant)
