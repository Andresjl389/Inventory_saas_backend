"""Composition point for the blob store.

The S3 adapter is not written yet; failing loudly here beats silently writing a
production deployment's invoices to a container's local disk.
"""

from functools import lru_cache

from app.domain.files.storage import FileStorage
from app.infrastructure.storage.local import LocalFileStorage
from app.shared.config.settings import settings


@lru_cache
def get_file_storage() -> FileStorage:
    if settings.storage_backend == "local":
        return LocalFileStorage(settings.storage_root)

    raise NotImplementedError(
        f"Storage backend {settings.storage_backend!r} is not implemented yet. "
        "Write a FileStorage adapter and register it here."
    )
