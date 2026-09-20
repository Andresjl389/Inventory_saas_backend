"""Arq worker.

Jobs are plain async functions that take the Arq context first; they can be
called directly from a test or a shell, which is why `sweep_low_stock` has a
default for it.
"""

from arq import cron
from arq.connections import RedisSettings

from app.infrastructure.database.session import dispose_engine
from app.infrastructure.jobs.file_maintenance import sweep_orphan_files
from app.infrastructure.jobs.low_stock import sweep_low_stock
from app.shared.config.settings import settings
from app.shared.logging.setup import configure_logging


async def startup(ctx: dict) -> None:
    configure_logging()


async def shutdown(ctx: dict) -> None:
    await dispose_engine()


class WorkerSettings:
    functions = [sweep_low_stock, sweep_orphan_files]
    cron_jobs = [
        # Every day at 07:00 server time, before the shop opens.
        cron(sweep_low_stock, hour=7, minute=0),
        # Reclaims blobs left behind by uploads that failed after writing.
        cron(sweep_orphan_files, hour=3, minute=30),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 300
