"""Port for the blob store.

Two implementations are expected: a local folder (today) and an S3-compatible
bucket (later). Nothing above this interface knows which one is in use, and the
key format is the adapter's business.
"""

from collections.abc import AsyncIterator
from typing import Protocol


class FileStorage(Protocol):
    async def save(self, key: str, chunks: AsyncIterator[bytes]) -> int:
        """Persist a stream under `key` and return the number of bytes written.

        Implementations write somewhere temporary and move the result into
        place, so a failed upload never leaves a half-written blob readable.
        """
        ...

    async def open(self, key: str) -> AsyncIterator[bytes]:
        """Stream the blob back. Raises FileNotFoundError when it is gone."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the blob. Idempotent: a missing key is not an error."""
        ...

    async def exists(self, key: str) -> bool: ...
