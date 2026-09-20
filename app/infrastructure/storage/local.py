"""Local filesystem blob store.

Good enough for development and for a single-node deployment with a mounted
volume. Swapping it for S3 means writing another `FileStorage` and changing one
line in the composition root -- nothing above the adapter refers to paths.

Two properties matter and are enforced here:

* writes are atomic -- the bytes land in a temp file and are moved into place,
  so a failed upload never leaves a readable half file;
* every resolved path is checked to be inside the root, even though keys are
  generated server-side. Cheap, and it makes the guarantee local to this file.
"""

import os
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import anyio

from app.domain.files.exceptions import FileNotFoundError as BlobNotFoundError

CHUNK_SIZE = 64 * 1024
TEMP_DIRNAME = ".tmp"


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()
        self._temp = self._root / TEMP_DIRNAME
        self._root.mkdir(parents=True, exist_ok=True)
        self._temp.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if not candidate.is_relative_to(self._root):
            # Unreachable with server-generated keys; a loud failure is still
            # better than writing outside the store if that ever changes.
            raise ValueError(f"Storage key escapes the root: {key!r}")
        return candidate

    async def save(self, key: str, chunks: AsyncIterator[bytes]) -> int:
        destination = self._path(key)
        staging = self._temp / f"{uuid.uuid4().hex}.part"
        written = 0

        # The directories are created in __init__, but the instance outlives
        # anything that might remove them (a cleanup script, a remounted
        # volume), so make sure they are there for each write.
        await anyio.to_thread.run_sync(lambda: self._temp.mkdir(parents=True, exist_ok=True))

        try:
            async with await anyio.open_file(staging, "wb") as handle:
                async for chunk in chunks:
                    await handle.write(chunk)
                    written += len(chunk)

            await anyio.to_thread.run_sync(
                lambda: destination.parent.mkdir(parents=True, exist_ok=True)
            )
            # os.replace is atomic within a filesystem; staging lives under the
            # same root precisely so that holds.
            await anyio.to_thread.run_sync(os.replace, staging, destination)
        except BaseException:
            await anyio.to_thread.run_sync(lambda: staging.unlink(missing_ok=True))
            raise

        return written

    async def open(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise BlobNotFoundError(f"No blob stored under {key!r}")

        async with await anyio.open_file(path, "rb") as handle:
            while chunk := await handle.read(CHUNK_SIZE):
                yield chunk

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await anyio.to_thread.run_sync(lambda: path.unlink(missing_ok=True))

    async def exists(self, key: str) -> bool:
        return await anyio.to_thread.run_sync(self._path(key).is_file)

    async def iter_entries(self) -> AsyncIterator[tuple[str, float]]:
        """Every stored key with its modification time, for the orphan sweep.

        The mtime is what lets the sweep skip a blob that was written seconds
        ago and whose database row is still uncommitted.
        """

        def walk() -> list[tuple[str, float]]:
            entries = []
            for path in self._root.rglob("*"):
                if path.is_file() and TEMP_DIRNAME not in path.parts:
                    entries.append((str(path.relative_to(self._root)), path.stat().st_mtime))
            return entries

        for entry in await anyio.to_thread.run_sync(walk):
            yield entry

    async def purge_staging(self) -> int:
        """Drop leftovers from uploads that died mid-write."""

        def clean() -> int:
            removed = 0
            for path in self._temp.glob("*.part"):
                path.unlink(missing_ok=True)
                removed += 1
            return removed

        return await anyio.to_thread.run_sync(clean)

    async def remove_company_tree(self, company_id: uuid.UUID) -> None:
        """Used when a company is deleted; the database rows go with it."""
        path = self._path(str(company_id))
        await anyio.to_thread.run_sync(lambda: shutil.rmtree(path, ignore_errors=True))
