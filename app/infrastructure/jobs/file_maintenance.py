"""Reclaims blobs that no database row points at.

Uploads write the blob before the metadata row, so a request that fails in
between leaves bytes behind. That trade is deliberate -- the alternative is a
row pointing at nothing, which is a broken download for a user rather than
wasted disk for the operator -- and this is the other half of it.

Only blobs older than the grace period are considered, so an upload whose row
is still in an uncommitted transaction is never swept away.
"""

import logging

from app.infrastructure.database.repositories.file_repository import SqlAlchemyFileRepository
from app.infrastructure.jobs.context import platform_session
from app.infrastructure.storage.local import LocalFileStorage

logger = logging.getLogger("app.jobs.file_maintenance")

GRACE_SECONDS = 3600


async def sweep_orphan_files(ctx: dict | None = None, *, dry_run: bool = False) -> dict[str, int]:
    from time import time

    from app.infrastructure.storage.factory import get_file_storage

    storage = get_file_storage()
    if not isinstance(storage, LocalFileStorage):
        # An object store lists its own bucket; that sweep belongs to its
        # adapter, not here.
        logger.info("orphan sweep skipped: not a local store")
        return {"scanned": 0, "removed": 0, "skipped": 1}

    # The platform flag is what makes this safe: with RLS narrowing the query,
    # another tenant's live blobs would look like orphans.
    async with platform_session() as session:
        known = await SqlAlchemyFileRepository(session).all_storage_keys()

    cutoff = time() - GRACE_SECONDS
    scanned = removed = 0

    async for key, mtime in storage.iter_entries():
        scanned += 1
        if key in known or mtime > cutoff:
            continue
        if not dry_run:
            await storage.delete(key)
        removed += 1

    staged = await storage.purge_staging()
    logger.info(
        "orphan sweep finished",
        extra={"scanned": scanned, "removed": removed, "staging_cleared": staged},
    )
    return {"scanned": scanned, "removed": removed, "staging_cleared": staged}
