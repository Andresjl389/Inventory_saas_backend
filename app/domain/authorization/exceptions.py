from app.shared.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError


class RoleNotFoundError(NotFoundError):
    code = "ROLE_NOT_FOUND"
    message = "Role not found"


class DuplicateRoleCodeError(ConflictError):
    code = "DUPLICATE_ROLE_CODE"
    message = "A role with that code already exists in this company"


class SystemRoleImmutableError(ForbiddenError):
    code = "SYSTEM_ROLE_IMMUTABLE"
    message = "System roles cannot be modified by a company"


class UnknownPermissionError(ValidationError):
    code = "UNKNOWN_PERMISSION"
    message = "Unknown permission code"


class RoleInUseError(ConflictError):
    code = "ROLE_IN_USE"
    message = "That role is still assigned to company members"
