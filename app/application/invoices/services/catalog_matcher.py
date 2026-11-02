"""Emparejar los renglones de un escaneo con el catálogo de la empresa.

Está separado de la lectura a propósito: el papel se lee una vez (y cuesta),
pero el catálogo cambia todo el tiempo. Volver a emparejar después de crear un
producto es gratis y es justo lo que pasa en la vida real -- se escanea la
factura, se cae en cuenta de que faltan tres productos, se crean, y los
renglones que estaban en el aire se acomodan solos.
"""

import uuid
from collections.abc import Iterable

from app.domain.invoices.entities.scan import LineAction, ScanLine
from app.domain.invoices.matching import ProductCandidate, match_product
from app.domain.products.repositories.product_repository import ProductRepository
from app.domain.shared.pagination import MAX_PAGE_SIZE, Page

DEFAULT_LIMIT = 5000


class CatalogMatcher:
    def __init__(self, products: ProductRepository, *, limit: int = DEFAULT_LIMIT) -> None:
        self._products = products
        self._limit = limit

    async def candidates(self, company_id: uuid.UUID) -> list[ProductCandidate]:
        """El catálogo activo, paginado hasta el tope.

        Se trae completo porque emparejar es comparar contra todo: una consulta
        por renglón sería una búsqueda por texto en la base, que es exactamente
        lo que no sirve cuando el proveedor abrevia distinto.
        """
        candidates: list[ProductCandidate] = []
        number = 1
        while len(candidates) < self._limit:
            result = await self._products.list(
                company_id, page=Page(number=number, size=MAX_PAGE_SIZE), is_active=True
            )
            candidates.extend(
                ProductCandidate(
                    product_id=product.id,
                    name=product.name,
                    sku=product.sku,
                    barcode=product.barcode,
                )
                for product in result.items
            )
            if number >= result.pages or not result.items:
                break
            number += 1
        return candidates[: self._limit]

    async def apply(
        self, lines: Iterable[ScanLine], *, company_id: uuid.UUID, only_pending: bool = False
    ) -> int:
        """Poner la propuesta en cada renglón. Devuelve cuántos quedaron
        enlazados solos.

        `only_pending=True` no toca lo que una persona ya decidió: volver a
        emparejar nunca debe deshacer una revisión.
        """
        targets = [line for line in lines if not only_pending or line.action is LineAction.PENDING]
        if not targets:
            return 0

        candidates = await self.candidates(company_id)
        linked = 0
        for line in targets:
            line.apply_suggestion(match_product(line.description, candidates, code=line.code))
            if line.action is LineAction.LINK:
                linked += 1
        return linked
