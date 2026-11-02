import uuid
from typing import Protocol

from app.domain.invoices.entities.scan import InvoiceScan, ScanStatus
from app.domain.shared.pagination import Page, PaginatedResult


class InvoiceScanRepository(Protocol):
    """Igual que las ventas y las compras: el escaneo se guarda completo, con
    sus renglones, porque revisarlo renglón por renglón no tiene sentido."""

    async def get_by_id(self, company_id: uuid.UUID, scan_id: uuid.UUID) -> InvoiceScan | None: ...

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        status: ScanStatus | None = None,
    ) -> PaginatedResult[InvoiceScan]: ...

    async def add(self, scan: InvoiceScan) -> InvoiceScan: ...

    async def save(self, scan: InvoiceScan) -> InvoiceScan:
        """Guardar encabezado y renglones de un escaneo abierto.

        Reemplaza los renglones en bloque: una revisión puede cambiar varios a
        la vez y reconciliar fila por fila solo abre la puerta a un estado
        intermedio raro.
        """
        ...
