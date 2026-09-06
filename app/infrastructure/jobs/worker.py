"""Arq worker.

Placeholder for phase 4 (low-stock alerts, report generation, imports/exports).
It boots today so `docker compose up` brings the full topology online.
"""

from arq.connections import RedisSettings

from app.shared.config.settings import settings
from app.shared.logging.setup import configure_logging


async def startup(ctx: dict) -> None:
    configure_logging()


class WorkerSettings:
    functions: list = []
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
