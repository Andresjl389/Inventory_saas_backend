"""Lo que dice una factura, una vez que algo la leyó.

Datos puros y el puerto que los produce. El puerto es deliberadamente tonto:
recibe bytes y devuelve lo que el papel dice, sin saber que existen productos,
proveedores ni compras. Emparejar los renglones con el catálogo es un paso
aparte -- así se puede probar sin ningún modelo y se puede volver a correr
cuando el catálogo cambia, sin volver a pagar la lectura.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.domain.shared.money import ZERO, money


@dataclass(frozen=True, slots=True)
class ExtractedLine:
    """Un renglón tal como está impreso, ya convertido a números.

    `total` es el total que trae el papel, no el que calculamos: cuando los dos
    no coinciden es señal de que la lectura falló en algo, y eso es justo lo que
    la pantalla de revisión tiene que mostrar.
    """

    description: str
    quantity: Decimal
    unit_cost: Decimal
    code: str | None = None
    unit: str | None = None
    discount: Decimal = ZERO
    tax: Decimal = ZERO
    total: Decimal | None = None
    # Qué tan segura fue la lectura de este renglón (1.0 = impreso y nítido).
    confidence: float = 1.0
    warnings: tuple[str, ...] = ()

    @property
    def computed_total(self) -> Decimal:
        return money(self.quantity * self.unit_cost - self.discount + self.tax)

    @property
    def total_mismatch(self) -> Decimal:
        """Diferencia entre el total impreso y el que dan las cuentas."""
        if self.total is None:
            return ZERO
        return money(self.total - self.computed_total)


@dataclass(frozen=True, slots=True)
class ExtractedInvoice:
    lines: tuple[ExtractedLine, ...] = ()
    supplier_name: str | None = None
    supplier_tax_id: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    # Qué adaptador (y con qué modelo) la leyó. Queda en el registro del
    # escaneo para poder comparar lecturas cuando se cambie de proveedor.
    source: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def lines_total(self) -> Decimal:
        return money(sum((line.computed_total for line in self.lines), ZERO))

    @property
    def total_mismatch(self) -> Decimal:
        """Lo que falta (o sobra) para que los renglones den el total impreso.

        Cero no prueba que la lectura esté bien, pero algo distinto de cero
        prueba que está mal: faltó un renglón, se leyó una cifra de más o el
        papel traía un cargo que no es mercancía.
        """
        if self.total is None:
            return ZERO
        return money(self.total - self.lines_total)


class InvoiceExtractor(Protocol):
    """Puerto de lectura. Una implementación usa un modelo de visión; otra, en
    pruebas, lee un formato de texto fijo."""

    @property
    def source(self) -> str:
        """Nombre del adaptador y su modelo, para dejarlo en el registro."""
        ...

    async def extract(
        self, payload: bytes, content_type: str, filename: str = ""
    ) -> ExtractedInvoice: ...
