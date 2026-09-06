from app.shared.exceptions import ConflictError, NotFoundError, UnauthorizedError


class UserNotFoundError(NotFoundError):
    code = "USER_NOT_FOUND"
    message = "User not found"


class EmailAlreadyRegisteredError(ConflictError):
    code = "EMAIL_ALREADY_REGISTERED"
    message = "That email address is already registered"


class InvalidCredentialsError(UnauthorizedError):
    code = "INVALID_CREDENTIALS"
    message = "Invalid email or password"


class InactiveUserError(UnauthorizedError):
    code = "INACTIVE_USER"
    message = "This account is disabled"
