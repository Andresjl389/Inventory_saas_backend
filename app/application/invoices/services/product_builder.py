"""Crear el producto que nace de un renglón de factura.

Es la parte que vuelve útil el escaneo para una tienda que arranca sin
catálogo: la primera factura que entra lo construye. Dos cuidados:

* el SKU se genera de la descripción y se verifica libre, porque un SKU
  repetido tumbaría toda la confirmación por un renglón;
* el código impreso se usa como código de barras solo si parece uno y está
  libre. Un número de referencia interno del proveedor metido en el campo de
  código de barras rompería después el escaneo del lector en el mostrador.
"""

import uuid

from app.application.invoices.dto.scan import NewProductCommand
from app.domain.invoices.entities.scan import ScanLine
from app.domain.products.entities.product import Product
from app.domain.products.repositories.product_repository import ProductRepository
from app.domain.shared.money import ZERO
from app.domain.shared.text import fold
from app.domain.tenants.tenant_context import TenantContext

MAX_NAME = 200
MAX_SKU = 64
SKU_WORDS = 3
SKU_BASE_LENGTH = 20
SKU_ATTEMPTS = 50
# Códigos de barras reales tienen 8 dígitos (EAN-8) o más.
MIN_BARCODE_DIGITS = 8


def _sku_base(description: str) -> str:
    words = [word for word in fold(description).split() if word][:SKU_WORDS]
    base = "-".join(words).upper()[:SKU_BASE_LENGTH].strip("-")
    return base or "ITEM"


class ProductBuilder:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    async def create(
        self, line: ScanLine, *, tenant: TenantContext, requested: NewProductCommand | None = None
    ) -> Product:
        wanted = requested or NewProductCommand()
        name = (wanted.name or line.description)[:MAX_NAME]
        sku = (
            wanted.sku.strip().upper()[:MAX_SKU]
            if wanted.sku
            else await self._free_sku(tenant.company_id, line.description)
        )

        return await self._products.add(
            Product(
                company_id=tenant.company_id,
                name=name,
                sku=sku,
                description=line.description if name != line.description else None,
                barcode=await self._usable_barcode(tenant.company_id, wanted.barcode or line.code),
                category_id=wanted.category_id,
                # El costo sí lo sabemos: lo dice la factura.
                cost_price=line.unit_cost,
                sale_price=wanted.sale_price if wanted.sale_price is not None else ZERO,
                min_stock=wanted.min_stock if wanted.min_stock is not None else ZERO,
            )
        )

    async def _free_sku(self, company_id: uuid.UUID, description: str) -> str:
        base = _sku_base(description)
        for attempt in range(1, SKU_ATTEMPTS + 1):
            candidate = base if attempt == 1 else f"{base}-{attempt}"
            if await self._products.get_by_sku(company_id, candidate) is None:
                return candidate
        # Cincuenta productos que empiezan igual: deja de contar y desempata.
        return f"{base}-{uuid.uuid4().hex[:6].upper()}"

    async def _usable_barcode(self, company_id: uuid.UUID, code: str | None) -> str | None:
        if not code:
            return None
        digits = "".join(character for character in code if character.isdigit())
        if len(digits) < MIN_BARCODE_DIGITS or digits != code.strip():
            return None
        if await self._products.get_by_barcode(company_id, digits) is not None:
            return None
        return digits
