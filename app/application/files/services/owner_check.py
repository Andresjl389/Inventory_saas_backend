"""Does the thing this file claims to belong to actually exist in this company?

`files.owner_id` has no foreign key -- it points at whichever table
`owner_type` names -- so the check lives here instead of in the schema. Without
it a client could attach files to ids that do not exist, or to another tenant's
records, and the orphan sweep would never notice.
"""

import uuid

from app.domain.files.entities.stored_file import FileOwnerType
from app.domain.products.repositories.product_repository import ProductRepository
from app.domain.purchases.repositories.purchase_repository import PurchaseRepository
from app.domain.sales.repositories.sale_repository import SaleRepository
from app.domain.tenants.tenant_context import TenantContext
from app.shared.exceptions import NotFoundError, ValidationError

# Owner types that stand for the company itself or for a process, and so carry
# no owner_id.
UNSCOPED_OWNER_TYPES = frozenset(
    {
        FileOwnerType.COMPANY,
        FileOwnerType.IMPORT,
        FileOwnerType.EXPORT,
        FileOwnerType.REPORT,
    }
)


class OwnerCheck:
    def __init__(
        self,
        products: ProductRepository,
        sales: SaleRepository,
        purchases: PurchaseRepository,
    ) -> None:
        self._products = products
        self._sales = sales
        self._purchases = purchases

    async def assert_valid(
        self,
        owner_type: FileOwnerType,
        owner_id: uuid.UUID | None,
        *,
        tenant: TenantContext,
    ) -> None:
        if owner_type in UNSCOPED_OWNER_TYPES:
            return

        if owner_id is None:
            raise ValidationError(
                f"owner_id is required for {owner_type.value} attachments",
                code="OWNER_ID_REQUIRED",
            )

        lookup = {
            FileOwnerType.PRODUCT: self._products.get_by_id,
            FileOwnerType.SALE: self._sales.get_by_id,
            FileOwnerType.PURCHASE: self._purchases.get_by_id,
        }[owner_type]

        # Each repository filters by company_id and runs under RLS, so another
        # tenant's record simply is not there.
        if await lookup(tenant.company_id, owner_id) is None:
            raise NotFoundError(
                f"No {owner_type.value.lower()} with that id in this company",
                code=f"{owner_type.value}_NOT_FOUND",
            )
