"""Escanear una factura: leer, revisar, confirmar.

Tres pasos y uno solo escribe en la empresa. Es la misma forma del importador
de Excel, por la misma razón: lo que entra al inventario tiene que haber pasado
por los ojos de alguien. La diferencia es que aquí el origen es una foto, así
que la revisión no es un trámite -- es donde se corrige lo que el modelo leyó
mal.

Qué hace cada paso:

1. `ScanInvoiceUseCase` -- lee el papel, propone proveedor y productos, y
   guarda todo como propuestas. No toca inventario, catálogo ni compras.
2. `ReviewScanUseCase` -- guarda las decisiones de una persona. Sigue sin
   tocar nada más.
3. `ConfirmScanUseCase` -- crea los productos nuevos y la compra. Es el único
   que escribe, y reusa el caso de uso de compras en vez de mover inventario
   por su cuenta: hay un solo camino por el que entra mercancía.
"""

import uuid
from decimal import Decimal

from app.application.files.dto.file import FileDTO
from app.application.invoices.dto.scan import (
    ConfirmScanCommand,
    ConfirmScanResultDTO,
    InvoiceScanDTO,
    LineDecisionCommand,
    ListScansQuery,
    NewProductCommand,
    ReviewScanCommand,
    ScanPageDTO,
)
from app.application.invoices.services.catalog_matcher import CatalogMatcher
from app.application.invoices.services.product_builder import ProductBuilder
from app.application.invoices.services.references import ReferenceCheck
from app.application.purchases.dto.purchase import (
    CreatePurchaseCommand,
    PurchaseItemCommand,
)
from app.application.purchases.use_cases.purchase_use_cases import CreatePurchaseUseCase
from app.domain.invoices.entities.scan import InvoiceScan, LineAction, ScanLine, ScanStatus
from app.domain.invoices.exceptions import (
    EmptyInvoiceError,
    InvoiceScanNotFoundError,
)
from app.domain.invoices.extraction import ExtractedInvoice, InvoiceExtractor
from app.domain.invoices.repositories.scan_repository import InvoiceScanRepository
from app.domain.shared.pagination import MAX_PAGE_SIZE, Page
from app.domain.shared.text import fold
from app.domain.suppliers.repositories.supplier_repository import SupplierRepository
from app.domain.tenants.tenant_context import TenantContext

SUPPLIER_SEARCH_SIZE = 20


def _to_dto(scan: InvoiceScan) -> InvoiceScanDTO:
    return InvoiceScanDTO.model_validate(scan, from_attributes=True)


class _ScanLookup:
    _scans: InvoiceScanRepository

    async def _load(self, scan_id: uuid.UUID, *, tenant: TenantContext) -> InvoiceScan:
        scan = await self._scans.get_by_id(tenant.company_id, scan_id)
        if scan is None:
            raise InvoiceScanNotFoundError()
        return scan


class ScanInvoiceUseCase:
    """Paso 1: leer la foto y proponer."""

    def __init__(
        self,
        scans: InvoiceScanRepository,
        extractor: InvoiceExtractor,
        matcher: CatalogMatcher,
        suppliers: SupplierRepository,
        references: ReferenceCheck,
    ) -> None:
        self._scans = scans
        self._extractor = extractor
        self._matcher = matcher
        self._suppliers = suppliers
        self._references = references

    async def execute(
        self,
        *,
        payload: bytes,
        stored_file: FileDTO,
        tenant: TenantContext,
        warehouse_id: uuid.UUID | None = None,
    ) -> InvoiceScanDTO:
        if warehouse_id is not None:
            await self._references.assert_warehouse(tenant.company_id, warehouse_id)

        extracted = await self._extractor.extract(
            payload, stored_file.content_type, stored_file.filename
        )
        if not extracted.lines:
            raise EmptyInvoiceError(
                "No se encontró ningún renglón en ese documento",
                details={"warnings": list(extracted.warnings)},
            )

        scan_id = uuid.uuid4()
        lines = [
            ScanLine(
                company_id=tenant.company_id,
                scan_id=scan_id,
                line_number=number,
                description=line.description,
                code=line.code,
                unit=line.unit,
                quantity=line.quantity,
                unit_cost=line.unit_cost,
                discount=line.discount,
                tax=line.tax,
                declared_total=line.total,
                confidence=_confidence(line.confidence),
                warnings=list(line.warnings),
            )
            for number, line in enumerate(extracted.lines, start=1)
        ]
        await self._matcher.apply(lines, company_id=tenant.company_id)

        scan = InvoiceScan(
            id=scan_id,
            company_id=tenant.company_id,
            file_id=stored_file.id,
            filename=stored_file.filename,
            supplier_name=extracted.supplier_name,
            supplier_tax_id=extracted.supplier_tax_id,
            supplier_id=await self._resolve_supplier(extracted, tenant=tenant),
            warehouse_id=warehouse_id,
            invoice_number=extracted.invoice_number,
            invoice_date=extracted.invoice_date,
            currency=extracted.currency,
            declared_subtotal=extracted.subtotal,
            declared_tax=extracted.tax,
            declared_total=extracted.total,
            extraction={
                "source": extracted.source,
                "warnings": list(extracted.warnings),
                "lines_read": len(extracted.lines),
                # La lectura cruda, antes de que nadie la corrija. Cuesta unos
                # kilobytes y es el único insumo con el que después se puede
                # medir qué tan bien lee el modelo propio en facturas de
                # verdad -- y entrenar uno a la medida con las correcciones.
                "read": _as_read(extracted),
            },
            created_by=tenant.user_id,
            lines=lines,
        )
        return _to_dto(await self._scans.add(scan))

    async def _resolve_supplier(
        self, extracted: ExtractedInvoice, *, tenant: TenantContext
    ) -> uuid.UUID | None:
        """A qué proveedor del sistema apunta el papel.

        Solo una coincidencia exacta -- el mismo NIT o el mismo nombre ya
        normalizado -- se acepta sola. Un parecido se deja sin resolver para
        que la revisión lo elija: comprarle sin darse cuenta al proveedor
        equivocado es un problema de plata, no de catálogo.
        """
        if extracted.supplier_tax_id:
            digits = "".join(
                character for character in extracted.supplier_tax_id if character.isdigit()
            )
            if digits:
                found = await self._suppliers.list(
                    tenant.company_id,
                    page=Page(number=1, size=SUPPLIER_SEARCH_SIZE),
                    search=extracted.supplier_tax_id,
                    is_active=True,
                )
                for supplier in found.items:
                    stored = "".join(
                        character
                        for character in (supplier.document_number or "")
                        if character.isdigit()
                    )
                    if stored and stored == digits:
                        return supplier.id

        if extracted.supplier_name:
            found = await self._suppliers.list(
                tenant.company_id,
                page=Page(number=1, size=SUPPLIER_SEARCH_SIZE),
                search=extracted.supplier_name,
                is_active=True,
            )
            wanted = fold(extracted.supplier_name)
            for supplier in found.items:
                if fold(supplier.name) == wanted:
                    return supplier.id

        return None


def _as_read(extracted: ExtractedInvoice) -> dict:
    """La lectura del modelo, tal como llegó, para poder compararla luego."""
    return {
        "supplier_name": extracted.supplier_name,
        "supplier_tax_id": extracted.supplier_tax_id,
        "invoice_number": extracted.invoice_number,
        "invoice_date": extracted.invoice_date.isoformat() if extracted.invoice_date else None,
        "total": str(extracted.total) if extracted.total is not None else None,
        "lines": [
            {
                "description": line.description,
                "code": line.code,
                "quantity": str(line.quantity),
                "unit_cost": str(line.unit_cost),
                "total": str(line.total) if line.total is not None else None,
                "confidence": line.confidence,
            }
            for line in extracted.lines
        ],
    }


def _confidence(value: float) -> Decimal:
    """La confianza del modelo, acotada a lo que la columna acepta."""
    return Decimal(str(round(max(0.0, min(1.0, value)), 4)))


class ReviewScanUseCase(_ScanLookup):
    """Paso 2: guardar lo que decidió una persona."""

    def __init__(self, scans: InvoiceScanRepository, references: ReferenceCheck) -> None:
        self._scans = scans
        self._references = references

    async def execute(
        self, scan_id: uuid.UUID, command: ReviewScanCommand, *, tenant: TenantContext
    ) -> InvoiceScanDTO:
        scan = await self._load(scan_id, tenant=tenant)
        scan.require_open()

        if command.warehouse_id is not None:
            await self._references.assert_warehouse(tenant.company_id, command.warehouse_id)
            scan.warehouse_id = command.warehouse_id
        if command.supplier_id is not None:
            await self._references.assert_supplier(tenant.company_id, command.supplier_id)
            scan.supplier_id = command.supplier_id
        if command.invoice_number is not None:
            scan.invoice_number = command.invoice_number or None
        if command.invoice_date is not None:
            scan.invoice_date = command.invoice_date
        if command.notes is not None:
            scan.notes = command.notes or None

        by_id = {line.id: line for line in scan.lines}
        for decision in command.lines:
            line = by_id.get(decision.line_id)
            if line is None:
                raise InvoiceScanNotFoundError(
                    "Ese renglón no pertenece a este escaneo",
                    details={"line_id": str(decision.line_id)},
                )
            await self._apply(line, decision, tenant=tenant)

        # El estado lo dice el trabajo que falta, no el botón que se apretó:
        # queda REVIEWED solo cuando no hay renglones sin decidir.
        scan.status = ScanStatus.REVIEWED if scan.pending_count == 0 else ScanStatus.EXTRACTED
        scan.touch()
        return _to_dto(await self._scans.save(scan))

    async def _apply(
        self, line: ScanLine, decision: LineDecisionCommand, *, tenant: TenantContext
    ) -> None:
        if decision.action is LineAction.LINK and decision.product_id is not None:
            await self._references.assert_product(tenant.company_id, decision.product_id)

        line.decide(
            decision.action,
            product_id=decision.product_id,
            quantity_=decision.quantity,
            unit_cost=decision.unit_cost,
            discount=decision.discount,
            tax=decision.tax,
            description=decision.description,
            new_product=(
                decision.new_product.model_dump(mode="json", exclude_none=True)
                if decision.new_product is not None
                else None
            ),
        )


class ConfirmScanUseCase(_ScanLookup):
    """Paso 3: crear los productos nuevos y la compra.

    Reusa `CreatePurchaseUseCase` en vez de mover inventario por su cuenta. No
    es economía de código: es que el inventario tenga un solo camino de entrada,
    con las mismas validaciones y el mismo libro de movimientos, venga la compra
    de un formulario o de una foto.
    """

    def __init__(
        self,
        scans: InvoiceScanRepository,
        create_purchase: CreatePurchaseUseCase,
        product_builder: ProductBuilder,
    ) -> None:
        self._scans = scans
        self._create_purchase = create_purchase
        self._product_builder = product_builder

    async def execute(
        self, scan_id: uuid.UUID, command: ConfirmScanCommand, *, tenant: TenantContext
    ) -> ConfirmScanResultDTO:
        scan = await self._load(scan_id, tenant=tenant)
        # Antes de crear nada: si falta algo, que falte con el catálogo intacto.
        scan.require_confirmable()

        created: list[uuid.UUID] = []
        for line in scan.lines:
            if line.action is not LineAction.CREATE:
                continue
            product = await self._product_builder.create(
                line,
                tenant=tenant,
                requested=(
                    NewProductCommand.model_validate(line.new_product) if line.new_product else None
                ),
            )
            created.append(product.id)
            line.link_created_product(product.id, sku=product.sku)

        # `require_confirmable` ya exigió la bodega.
        purchase = await self._create_purchase.execute(
            CreatePurchaseCommand(
                warehouse_id=scan.warehouse_id,
                supplier_id=scan.supplier_id,
                items=[
                    PurchaseItemCommand(
                        product_id=line.product_id,
                        quantity=line.quantity,
                        unit_cost=line.unit_cost,
                        discount=line.discount,
                        tax=line.tax,
                    )
                    for line in scan.merchandise
                ],
                notes=_purchase_notes(scan),
                complete=command.complete,
                update_product_costs=command.update_product_costs,
            ),
            tenant=tenant,
        )

        scan.confirm(purchase.id)
        saved = await self._scans.save(scan)
        return ConfirmScanResultDTO(
            scan=_to_dto(saved), purchase=purchase, created_product_ids=created
        )


def _purchase_notes(scan: InvoiceScan) -> str:
    """De dónde salió esta compra, legible en la lista de compras."""
    parts = ["Factura escaneada"]
    if scan.invoice_number:
        parts.append(f"No. {scan.invoice_number}")
    if scan.supplier_name:
        parts.append(f"de {scan.supplier_name}")
    note = " ".join(parts)
    return f"{note}. {scan.notes}"[:1000] if scan.notes else note[:1000]


class RematchScanUseCase(_ScanLookup):
    """Volver a emparejar los renglones sin decidir contra el catálogo de ahora.

    Es gratis -- no vuelve a leer el papel -- y es el caso real: se escanea,
    se cae en cuenta de que faltaban productos, se crean, y esto acomoda los
    renglones que quedaron en el aire. Nunca toca un renglón ya decidido.
    """

    def __init__(self, scans: InvoiceScanRepository, matcher: CatalogMatcher) -> None:
        self._scans = scans
        self._matcher = matcher

    async def execute(self, scan_id: uuid.UUID, *, tenant: TenantContext) -> InvoiceScanDTO:
        scan = await self._load(scan_id, tenant=tenant)
        scan.require_open()
        await self._matcher.apply(scan.lines, company_id=tenant.company_id, only_pending=True)
        scan.touch()
        return _to_dto(await self._scans.save(scan))


class GetScanUseCase(_ScanLookup):
    def __init__(self, scans: InvoiceScanRepository) -> None:
        self._scans = scans

    async def execute(self, scan_id: uuid.UUID, *, tenant: TenantContext) -> InvoiceScanDTO:
        return _to_dto(await self._load(scan_id, tenant=tenant))


class ListScansUseCase:
    def __init__(self, scans: InvoiceScanRepository) -> None:
        self._scans = scans

    async def execute(self, query: ListScansQuery, *, tenant: TenantContext) -> ScanPageDTO:
        result = await self._scans.list(
            tenant.company_id,
            page=Page(number=query.page, size=min(query.size, MAX_PAGE_SIZE)),
            status=query.status,
        )
        return ScanPageDTO(
            items=[_to_dto(row) for row in result.items],
            total=result.total,
            page=result.page.number,
            size=result.page.size,
            pages=result.pages,
        )


class CancelScanUseCase(_ScanLookup):
    def __init__(self, scans: InvoiceScanRepository) -> None:
        self._scans = scans

    async def execute(self, scan_id: uuid.UUID, *, tenant: TenantContext) -> InvoiceScanDTO:
        scan = await self._load(scan_id, tenant=tenant)
        scan.cancel()
        return _to_dto(await self._scans.save(scan))
