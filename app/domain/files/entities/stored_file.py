"""A file attached to something in a company.

The row is the source of truth: it carries the tenant, the owner, the original
name and where the bytes live. The blob itself is opaque to the domain, which
is what lets the storage move from a local folder to S3 without touching
anything above the adapter.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.domain.shared.entities import TenantEntity


class FileOwnerType(StrEnum):
    """What the file is attached to. PRODUCT covers product images."""

    PRODUCT = "PRODUCT"
    COMPANY = "COMPANY"
    SALE = "SALE"
    PURCHASE = "PURCHASE"
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    REPORT = "REPORT"


@dataclass(kw_only=True)
class StoredFile(TenantEntity):
    owner_type: FileOwnerType
    owner_id: uuid.UUID | None = None
    # What the user called it. Only ever echoed back in a download header,
    # never used to build a path.
    filename: str
    content_type: str
    size_bytes: int
    # Where the adapter put the bytes. Generated server-side; see
    # app.domain.files.keys.
    storage_key: str
    checksum: str
    uploaded_by: uuid.UUID | None = None

    @property
    def is_image(self) -> bool:
        return self.content_type.startswith("image/")
