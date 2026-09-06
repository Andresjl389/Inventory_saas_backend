"""Base exception hierarchy shared by every layer.

Domain and application code raise these; the presentation layer is the only
place that knows how to turn them into HTTP responses.
"""

from typing import Any


class AppError(Exception):
    """Root of every expected (handled) error in the system."""

    code: str = "INTERNAL_ERROR"
    message: str = "Unexpected error"
    status_code: int = 500

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    message = "Invalid input"
    status_code = 422


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    message = "Authentication required"
    status_code = 401


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    message = "Operation not allowed"
    status_code = 403


class NotFoundError(AppError):
    code = "RESOURCE_NOT_FOUND"
    message = "Resource not found"
    status_code = 404


class ConflictError(AppError):
    code = "CONFLICT"
    message = "Resource conflict"
    status_code = 409


class BusinessRuleError(AppError):
    code = "BUSINESS_RULE_VIOLATION"
    message = "Business rule violated"
    status_code = 422
