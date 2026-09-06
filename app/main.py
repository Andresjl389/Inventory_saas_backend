"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infrastructure.database.session import dispose_engine
from app.presentation.api.middleware.error_handler import register_exception_handlers
from app.presentation.api.middleware.request_context import RequestContextMiddleware
from app.presentation.api.v1 import health
from app.presentation.api.v1.router import api_router
from app.shared.config.settings import settings
from app.shared.logging.setup import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Multi-tenant inventory SaaS. Authenticate with /api/v1/auth/login, then send "
            "the active company in the X-Company-ID header."
        ),
        openapi_url=(None if settings.is_production else f"{settings.api_v1_prefix}/openapi.json"),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
