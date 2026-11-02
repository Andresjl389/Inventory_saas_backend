import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.application.purchases.dto.purchase import PurchaseDTO
from app.domain.invoices.entities.scan import LineAction, ScanStatus
from app.domain.shared.pagination import MAX_PAGE_SIZE


class NewProductCommand(BaseModel):
    """Lo que se quiera fijar del producto que nace de un renglón.

    Todo es opcional: sin nada, el nombre sale de la descripción impresa y el
    SKU se genera. Lo que no se adivina nunca es el precio de venta, que queda
    en cero -- ponerle uno inventado sería peor que dejarlo visible en cero.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    category_id: uuid.UUID | None = None
    sale_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    min_stock: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)


class LineDecisionCommand(BaseModel):
    """La decisión sobre un renglón, con las correcciones de cifras que casi
    siempre vienen con ella."""

    line_id: uuid.UUID
    action: LineAction
    product_id: uuid.UUID | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    discount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    tax: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    new_product: NewProductCommand | None = None


class ReviewScanCommand(BaseModel):
    """La pantalla de revisión manda el encabezado y los renglones que tocó.

    Los renglones que no vengan quedan como están: revisar una factura de
    cuarenta renglones es trabajo de varias pasadas.
    """

    supplier_id: uuid.UUID | None = None
    warehouse_id: uuid.UUID | None = None
    invoice_number: str | None = Field(default=None, max_length=64)
    invoice_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[LineDecisionCommand] = Field(default_factory=list)


class ConfirmScanCommand(BaseModel):
    # Una factura escaneada normalmente es mercancía que ya llegó, así que la
    # compra se completa y el inventario se mueve.
    complete: bool = True
    # Apagado por defecto, igual que en compras: muchos negocios quieren
    # promedio ponderado y no último costo, y eso es una decisión del negocio.
    update_product_costs: bool = False


class ScanLineDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    description: str
    code: str | None
    unit: str | None
    quantity: Decimal
    unit_cost: Decimal
    discount: Decimal
    tax: Decimal
    # Lo que dan las cuentas y lo que decía el papel. Cuando no coinciden,
    # `total_mismatch` es distinto de cero y la pantalla lo resalta.
    total: Decimal
    declared_total: Decimal | None
    total_mismatch: Decimal
    confidence: Decimal

    suggested_product_id: uuid.UUID | None
    match_confidence: Decimal
    match_reason: str

    action: LineAction
    product_id: uuid.UUID | None
    new_product: dict[str, Any]
    warnings: list[str]
    needs_review: bool


class InvoiceScanDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    file_id: uuid.UUID
    filename: str
    status: ScanStatus

    supplier_name: str | None
    supplier_tax_id: str | None
    supplier_id: uuid.UUID | None
    warehouse_id: uuid.UUID | None

    invoice_number: str | None
    invoice_date: date | None
    currency: str | None
    declared_subtotal: Decimal | None
    declared_tax: Decimal | None
    declared_total: Decimal | None

    notes: str | None
    extraction: dict[str, Any]
    purchase_id: uuid.UUID | None
    created_by: uuid.UUID | None
    failure_reason: str | None

    lines: list[ScanLineDTO]
    # El resumen que decide si se puede confirmar o no.
    lines_total: Decimal
    total_mismatch: Decimal
    pending_count: int
    review_count: int

    created_at: datetime
    updated_at: datetime


class ListScansQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=MAX_PAGE_SIZE)
    status: ScanStatus | None = None


class ScanPageDTO(BaseModel):
    items: list[InvoiceScanDTO]
    total: int
    page: int
    size: int
    pages: int


class ConfirmScanResultDTO(BaseModel):
    """Lo que dejó la confirmación: el escaneo cerrado, la compra que nació de
    él y los productos que no existían antes."""

    scan: InvoiceScanDTO
    purchase: PurchaseDTO
    created_product_ids: list[uuid.UUID] = Field(default_factory=list)
