"""Lector de facturas en texto plano: el adaptador determinista.

Existe por una razón concreta: todo el flujo de escaneo -- emparejar con el
catálogo, revisar, confirmar, crear la compra, mover el inventario -- se puede
probar y desarrollar sin llave de API, sin red y sin pagar una sola lectura. Lo
único que no cubre es la visión, que es justamente la parte que no tiene sentido
probar con asserts.

El formato es el que uno escribiría a mano:

    Proveedor: Distribuidora El Sol
    NIT: 900.123.456-7
    Factura: F-00123
    Fecha: 15/10/2026
    Total: 86.000
    ---
    2 | Arroz Diana 500g | 2.500
    3 | Aceite Premier 1L | 12.000 | 7702007037128

Encabezado como `clave: valor`, renglones separados por `|` en el orden
cantidad, descripción, costo unitario y, opcionales, código y total impreso.
"""

from decimal import Decimal

from app.domain.imports.coercion import CoercionError, to_date, to_decimal, to_text
from app.domain.invoices.exceptions import UnsupportedInvoiceFileError
from app.domain.invoices.extraction import ExtractedInvoice, ExtractedLine, InvoiceExtractor
from app.domain.shared.money import ZERO
from app.domain.shared.text import fold

SUPPORTED_TYPES = ("text/plain", "text/csv")
SEPARATOR = "|"

# Varias formas de escribir lo mismo, porque esto se teclea a mano.
HEADER_KEYS = {
    "proveedor": "supplier_name",
    "nit": "supplier_tax_id",
    "factura": "invoice_number",
    "numero": "invoice_number",
    "fecha": "invoice_date",
    "moneda": "currency",
    "subtotal": "subtotal",
    "impuesto": "tax",
    "iva": "tax",
    "total": "total",
}


def _decimal(raw: str, warnings: list[str], label: str) -> Decimal | None:
    try:
        return to_decimal(raw)
    except CoercionError:
        warnings.append(f"{label}: no se pudo leer {raw!r} como número")
        return None


class TextInvoiceExtractor(InvoiceExtractor):
    @property
    def source(self) -> str:
        return "text"

    async def extract(
        self, payload: bytes, content_type: str, filename: str = ""
    ) -> ExtractedInvoice:
        if content_type not in SUPPORTED_TYPES:
            raise UnsupportedInvoiceFileError(
                f"El lector de texto solo acepta {', '.join(SUPPORTED_TYPES)}",
                details={"allowed": list(SUPPORTED_TYPES)},
            )

        warnings: list[str] = []
        header: dict[str, str] = {}
        lines: list[ExtractedLine] = []

        for raw in payload.decode("utf-8", errors="replace").splitlines():
            row = raw.strip()
            if not row or set(row) <= {"-", "="}:
                continue
            if SEPARATOR in row:
                line = self._as_line(row, warnings)
                if line is not None:
                    lines.append(line)
            elif ":" in row:
                key, _, value = row.partition(":")
                target = HEADER_KEYS.get(fold(key))
                if target:
                    header[target] = value.strip()

        invoice_date = None
        if header.get("invoice_date"):
            try:
                invoice_date = to_date(header["invoice_date"])
            except CoercionError:
                warnings.append(f"fecha: no se pudo leer {header['invoice_date']!r}")

        return ExtractedInvoice(
            lines=tuple(lines),
            supplier_name=to_text(header.get("supplier_name")),
            supplier_tax_id=to_text(header.get("supplier_tax_id")),
            invoice_number=to_text(header.get("invoice_number")),
            invoice_date=invoice_date,
            currency=to_text(header.get("currency")),
            subtotal=_decimal(header["subtotal"], warnings, "subtotal")
            if header.get("subtotal")
            else None,
            tax=_decimal(header["tax"], warnings, "impuesto") if header.get("tax") else None,
            total=_decimal(header["total"], warnings, "total") if header.get("total") else None,
            source=self.source,
            warnings=tuple(warnings),
        )

    def _as_line(self, row: str, warnings: list[str]) -> ExtractedLine | None:
        cells = [cell.strip() for cell in row.split(SEPARATOR)]
        if len(cells) < 3:
            warnings.append(f"renglón incompleto, se omitió: {row!r}")
            return None

        description = to_text(cells[1])
        if not description:
            warnings.append(f"renglón sin descripción, se omitió: {row!r}")
            return None

        line_warnings: list[str] = []
        quantity = _decimal(cells[0], line_warnings, "cantidad")
        if quantity is None or quantity <= 0:
            line_warnings.append("cantidad ilegible: se asumió 1, confírmala")
            quantity = Decimal("1")

        unit_cost = _decimal(cells[2], line_warnings, "costo unitario")
        if unit_cost is None or unit_cost < 0:
            line_warnings.append("costo unitario ilegible: quedó en 0, escríbelo a mano")
            unit_cost = ZERO

        return ExtractedLine(
            description=description,
            quantity=quantity,
            unit_cost=unit_cost,
            code=to_text(cells[3]) if len(cells) > 3 else None,
            total=_decimal(cells[4], line_warnings, "total del renglón")
            if len(cells) > 4 and cells[4]
            else None,
            warnings=tuple(line_warnings),
        )
