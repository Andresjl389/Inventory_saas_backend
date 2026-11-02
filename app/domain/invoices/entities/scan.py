"""El escaneo de una factura de compra.

Igual que un import: primero se lee, después una persona revisa, y solo
entonces se escribe en la empresa. La diferencia es de dónde salen los datos --
una foto en vez de un archivo -- y eso vuelve la revisión más importante, no
menos: un modelo leyendo un papel arrugado se equivoca de maneras que un
archivo de Excel no.

De ahí la regla central: ningún renglón entra solo. El emparejador *propone*
(`suggested_product_id`, con su confianza) y la decisión vive aparte
(`action` + `product_id`). Solo un código de barras, un SKU o un nombre casi
idéntico se enlazan sin preguntar; el resto queda PENDING y confirmar con
renglones PENDING es un error, no un descarte silencioso.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.domain.invoices.exceptions import (
    NothingToPurchaseError,
    ScanNotOpenError,
    UndecidedLinesError,
    WarehouseRequiredError,
)
from app.domain.invoices.matching import AUTO_LINK, ProductMatch
from app.domain.shared.entities import BaseEntity, TenantEntity
from app.domain.shared.money import ZERO, money, quantity

MAX_DESCRIPTION = 500


class ScanStatus(StrEnum):
    EXTRACTED = "EXTRACTED"  # leída; los renglones traen propuestas
    REVIEWED = "REVIEWED"  # una persona decidió los renglones
    CONFIRMED = "CONFIRMED"  # se creó la compra
    FAILED = "FAILED"  # no se pudo leer
    CANCELLED = "CANCELLED"


class LineAction(StrEnum):
    PENDING = "PENDING"  # sin decidir: bloquea la confirmación
    LINK = "LINK"  # es este producto
    CREATE = "CREATE"  # producto nuevo, sale de este renglón
    SKIP = "SKIP"  # no es mercancía (flete, envase, impuesto suelto)


class InvalidScanLineError(ValueError):
    """Un renglón que no se puede ni guardar: la lectura tiene que corregirlo
    antes, no la base de datos después."""


@dataclass(kw_only=True)
class ScanLine(BaseEntity):
    company_id: uuid.UUID
    scan_id: uuid.UUID
    # El número del renglón en el papel, para que la revisión se pueda seguir
    # con la factura al lado.
    line_number: int
    description: str
    quantity: Decimal
    unit_cost: Decimal
    code: str | None = None
    unit: str | None = None
    discount: Decimal = ZERO
    tax: Decimal = ZERO
    # El total que trae impreso el renglón, no el que calculamos.
    declared_total: Decimal | None = None
    # Qué tan segura fue la lectura (no el emparejamiento).
    confidence: Decimal = Decimal("1")

    suggested_product_id: uuid.UUID | None = None
    match_confidence: Decimal = ZERO
    match_reason: str = "unmatched"

    action: LineAction = LineAction.PENDING
    product_id: uuid.UUID | None = None
    # Para action=CREATE: nombre, sku y precio de venta que quiera la persona.
    # Vacío significa "derívalo de la descripción".
    new_product: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.description = (self.description or "").strip()[:MAX_DESCRIPTION]
        if not self.description:
            raise InvalidScanLineError("Un renglón sin descripción no se puede revisar")

        self.quantity = quantity(self.quantity)
        self.unit_cost = money(self.unit_cost)
        self.discount = money(self.discount)
        self.tax = money(self.tax)
        if self.declared_total is not None:
            self.declared_total = money(self.declared_total)

        if self.quantity <= 0:
            raise InvalidScanLineError("La cantidad de un renglón tiene que ser mayor que cero")
        if self.unit_cost < 0 or self.discount < 0 or self.tax < 0:
            raise InvalidScanLineError("Los importes de un renglón no pueden ser negativos")
        if self.action is LineAction.LINK and self.product_id is None:
            raise InvalidScanLineError("Un renglón enlazado tiene que decir a qué producto")

    @property
    def total(self) -> Decimal:
        """Lo que cuesta este renglón según las cuentas."""
        return money(self.quantity * self.unit_cost - self.discount + self.tax)

    @property
    def total_mismatch(self) -> Decimal:
        if self.declared_total is None:
            return ZERO
        return money(self.declared_total - self.total)

    @property
    def is_merchandise(self) -> bool:
        """Entra al inventario cuando se confirme."""
        return self.action in (LineAction.LINK, LineAction.CREATE)

    @property
    def needs_review(self) -> bool:
        """Lo que la pantalla tiene que resaltar."""
        if self.action is LineAction.PENDING:
            return True
        if self.action is LineAction.LINK and self.match_confidence < Decimal(str(AUTO_LINK)):
            return True
        return bool(self.warnings) or self.total_mismatch != ZERO

    def apply_suggestion(self, match: ProductMatch) -> None:
        """Guardar lo que encontró el emparejador y, solo si es seguro,
        enlazar."""
        self.suggested_product_id = match.product_id
        self.match_confidence = Decimal(str(match.confidence))
        self.match_reason = match.reason
        if match.is_certain:
            self.action = LineAction.LINK
            self.product_id = match.product_id

    def link_created_product(self, product_id: uuid.UUID, *, sku: str) -> None:
        """El producto que este renglón pidió crear ya existe.

        Pasa a LINK porque la decisión se cumplió -- y porque la base exige que
        un renglón con producto esté enlazado -- pero deja escrito que el
        producto nació aquí. Si no, a los dos días nadie sabría de dónde salió
        ese "ARROZ DIANA 500G" con SKU autogenerado.
        """
        self.action = LineAction.LINK
        self.product_id = product_id
        self.new_product = {
            **self.new_product,
            "created_product_id": str(product_id),
            "created_sku": sku,
        }
        self.touch()

    def decide(
        self,
        action: LineAction,
        *,
        product_id: uuid.UUID | None = None,
        quantity_: Decimal | None = None,
        unit_cost: Decimal | None = None,
        discount: Decimal | None = None,
        tax: Decimal | None = None,
        description: str | None = None,
        new_product: dict[str, Any] | None = None,
    ) -> None:
        """La decisión de una persona sobre un renglón, con las correcciones
        de cifras que casi siempre vienen con ella."""
        if action is LineAction.LINK and product_id is None:
            raise InvalidScanLineError("Para enlazar hay que decir a qué producto")

        if description is not None:
            cleaned = description.strip()[:MAX_DESCRIPTION]
            if not cleaned:
                raise InvalidScanLineError("La descripción no puede quedar vacía")
            self.description = cleaned
        if quantity_ is not None:
            if quantity(quantity_) <= 0:
                raise InvalidScanLineError("La cantidad tiene que ser mayor que cero")
            self.quantity = quantity(quantity_)
        for name, value in (("unit_cost", unit_cost), ("discount", discount), ("tax", tax)):
            if value is None:
                continue
            if money(value) < 0:
                raise InvalidScanLineError(f"{name} no puede ser negativo")
            setattr(self, name, money(value))

        self.action = action
        # Enlazar y crear son excluyentes: dejar el producto puesto al pasar a
        # CREATE o SKIP haría una compra con un renglón que nadie pidió.
        self.product_id = product_id if action is LineAction.LINK else None
        if new_product is not None:
            self.new_product = new_product if action is LineAction.CREATE else {}
        elif action is not LineAction.CREATE:
            self.new_product = {}
        self.touch()


@dataclass(kw_only=True)
class InvoiceScan(TenantEntity):
    file_id: uuid.UUID
    filename: str
    status: ScanStatus = ScanStatus.EXTRACTED

    # Lo que decía el papel sobre quién la emitió, y a quién terminó apuntando.
    supplier_name: str | None = None
    supplier_tax_id: str | None = None
    supplier_id: uuid.UUID | None = None

    # A qué bodega entra la mercancía. Puede venir del escaneo o decidirse en
    # la revisión, pero sin ella no hay compra.
    warehouse_id: uuid.UUID | None = None

    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    declared_subtotal: Decimal | None = None
    declared_tax: Decimal | None = None
    declared_total: Decimal | None = None

    notes: str | None = None
    # Quién la leyó y qué avisó: adaptador, modelo, advertencias.
    extraction: dict[str, Any] = field(default_factory=dict)

    purchase_id: uuid.UUID | None = None
    created_by: uuid.UUID | None = None
    failure_reason: str | None = None
    lines: list[ScanLine] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.status in (ScanStatus.EXTRACTED, ScanStatus.REVIEWED)

    def require_open(self) -> None:
        if not self.is_open:
            raise ScanNotOpenError(
                f"Un escaneo en estado {self.status.value} ya no se puede modificar"
            )

    @property
    def merchandise(self) -> list[ScanLine]:
        return [line for line in self.lines if line.is_merchandise]

    @property
    def pending_count(self) -> int:
        return sum(1 for line in self.lines if line.action is LineAction.PENDING)

    @property
    def review_count(self) -> int:
        return sum(1 for line in self.lines if line.needs_review)

    @property
    def lines_total(self) -> Decimal:
        """El total de lo que se va a comprar: descartados no cuentan."""
        return money(sum((line.total for line in self.merchandise), ZERO))

    @property
    def total_mismatch(self) -> Decimal:
        """Diferencia contra el total impreso.

        Distinto de cero no siempre es un error -- un flete descartado explica
        la diferencia -- pero siempre es algo que hay que mirar antes de
        confirmar, y por eso viaja en la respuesta.
        """
        if self.declared_total is None:
            return ZERO
        return money(self.declared_total - self.lines_total)

    def require_confirmable(self) -> None:
        self.require_open()
        if self.warehouse_id is None:
            raise WarehouseRequiredError()
        if self.pending_count:
            raise UndecidedLinesError(
                f"Quedan {self.pending_count} renglones sin decidir",
                details={"pending": self.pending_count},
            )
        if not self.merchandise:
            raise NothingToPurchaseError()

    def mark_reviewed(self) -> None:
        self.require_open()
        self.status = ScanStatus.REVIEWED
        self.touch()

    def confirm(self, purchase_id: uuid.UUID) -> None:
        self.require_confirmable()
        self.purchase_id = purchase_id
        self.status = ScanStatus.CONFIRMED
        self.touch()

    def fail(self, reason: str) -> None:
        self.failure_reason = reason
        self.status = ScanStatus.FAILED
        self.touch()

    def cancel(self) -> None:
        self.require_open()
        self.status = ScanStatus.CANCELLED
        self.touch()
