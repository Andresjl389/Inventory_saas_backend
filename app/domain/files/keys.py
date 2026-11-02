"""Storage keys are generated here, never taken from the client.

This lives in the domain rather than in the storage adapter on purpose: how a
tenant's files are laid out is a decision the application makes, and the
application layer needs it to build a key before handing bytes to any adapter.
The adapter only ever receives a key it did not choose.

A key is built from the tenant, what the file belongs to, the date and a fresh
UUID, with an extension derived from the *content type* rather than from the
uploaded filename. That removes path traversal, double extensions and
`image.png.php` tricks as a class of problem instead of filtering for them.
"""

import re
import unicodedata
import uuid
from datetime import UTC, datetime

from app.domain.files.entities.stored_file import FileOwnerType

EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}

MAX_FILENAME_LENGTH = 120
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]")


def build_key(*, company_id: uuid.UUID, owner_type: FileOwnerType, content_type: str) -> str:
    now = datetime.now(UTC)
    extension = EXTENSION_BY_CONTENT_TYPE.get(content_type, ".bin")
    return f"{company_id}/{owner_type.value.lower()}/{now:%Y/%m}/{uuid.uuid4().hex}{extension}"


def safe_filename(raw: str) -> str:
    """Clean the display name.

    It is only ever echoed back in a Content-Disposition header, but a raw
    filename there can carry newlines or quotes and break the header, so it is
    normalised on the way in rather than on every way out.
    """
    name = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    name = _UNSAFE.sub("_", name).strip(". ")
    return (name or "file")[:MAX_FILENAME_LENGTH]
