from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.infrastructure.database.session import engine
from app.shared.config.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """The process is up. Never touches dependencies."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    """The process can reach its dependencies."""
    checks: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        checks["database"] = f"error: {exc.__class__.__name__}"

    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
