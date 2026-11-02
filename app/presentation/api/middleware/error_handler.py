"""Single place where errors become HTTP responses, in the format defined in
BACKEND.md section 38."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.config.settings import settings
from app.shared.exceptions import AppError

logger = logging.getLogger("app.errors")


def _error_response(status_code: int, code: str, message: str, details: dict | None = None):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code == 503:
            # Una capacidad apagada o una dependencia caída es operación
            # normal, no un defecto: queda el registro, sin traza.
            logger.warning("service unavailable", extra={"code": exc.code})
        elif exc.status_code >= 500:
            logger.exception("unhandled application error", exc_info=exc)
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            422,
            "VALIDATION_ERROR",
            "Request validation failed",
            {
                "fields": [
                    {"location": list(err["loc"]), "message": err["msg"], "type": err["type"]}
                    for err in exc.errors()
                ]
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "RESOURCE_NOT_FOUND"}
        return _error_response(
            exc.status_code,
            codes.get(exc.status_code, "HTTP_ERROR"),
            str(exc.detail),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        # A race can slip past the application-level uniqueness checks; the
        # database constraint is the authority.
        logger.warning("integrity error", extra={"detail": str(exc.orig)})
        return _error_response(409, "CONFLICT", "The operation conflicts with existing data")

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected error", exc_info=exc)
        message = str(exc) if settings.debug else "Unexpected error"
        return _error_response(500, "INTERNAL_ERROR", message)
