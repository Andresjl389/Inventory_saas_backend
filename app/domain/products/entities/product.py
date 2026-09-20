"""Product entity.

Money is `Decimal` everywhere -- never float (BACKEND.md section 12).
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.domain.products.exceptions import InvalidProductPriceError
from app.domain.shared.entities import TenantEntity

PRICE_SCALE = Decimal("0.0001")


@dataclass(kw_only=True)
class Product(TenantEntity):
    name: str
    sku: str
    description: str | None = None
    barcode: str | None = None
    category_id: uuid.UUID | None = None
    cost_price: Decimal = Decimal("0")
    sale_price: Decimal = Decimal("0")
    is_active: bool = True
    min_stock: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        self.sku = self.sku.strip().upper()
        self._validate_prices()

    def _validate_prices(self) -> None:
        if self.cost_price < 0:
            raise InvalidProductPriceError("Cost price cannot be negative")
        if self.sale_price < 0:
            raise InvalidProductPriceError("Sale price cannot be negative")

    def update_prices(self, *, cost_price: Decimal | None, sale_price: Decimal | None) -> None:
        if cost_price is not None:
            self.cost_price = cost_price
        if sale_price is not None:
            self.sale_price = sale_price
        self._validate_prices()
        self.touch()

    @property
    def margin(self) -> Decimal:
        """Absolute margin per unit."""
        return self.sale_price - self.cost_price

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()
