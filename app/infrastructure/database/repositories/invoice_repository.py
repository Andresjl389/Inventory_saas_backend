import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.invoices.entities.scan import InvoiceScan, ScanLine, ScanStatus
from app.domain.shared.pagination import Page, PaginatedResult
from app.infrastructure.database.models.invoice import InvoiceScanLineModel, InvoiceScanModel
from app.infrastructure.database.repositories.mappers import invoice_scan_to_domain


def _line_model(line: ScanLine, scan_id: uuid.UUID) -> InvoiceScanLineModel:
    return InvoiceScanLineModel(
        id=line.id,
        company_id=line.company_id,
        scan_id=scan_id,
        line_number=line.line_number,
        description=line.description,
        code=line.code,
        unit=line.unit,
        quantity=line.quantity,
        unit_cost=line.unit_cost,
        discount=line.discount,
        tax=line.tax,
        declared_total=line.declared_total,
        confidence=line.confidence,
        suggested_product_id=line.suggested_product_id,
        match_confidence=line.match_confidence,
        match_reason=line.match_reason,
        action=line.action,
        product_id=line.product_id,
        new_product=line.new_product,
        warnings=list(line.warnings),
    )


class SqlAlchemyInvoiceScanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, company_id: uuid.UUID, scan_id: uuid.UUID) -> InvoiceScan | None:
        stmt = select(InvoiceScanModel).where(
            InvoiceScanModel.id == scan_id, InvoiceScanModel.company_id == company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return invoice_scan_to_domain(model) if model else None

    async def list(
        self,
        company_id: uuid.UUID,
        *,
        page: Page,
        status: ScanStatus | None = None,
    ) -> PaginatedResult[InvoiceScan]:
        filters = [InvoiceScanModel.company_id == company_id]
        if status is not None:
            filters.append(InvoiceScanModel.status == status)

        total = (
            await self._session.execute(
                select(func.count()).select_from(InvoiceScanModel).where(*filters)
            )
        ).scalar_one()

        stmt = (
            select(InvoiceScanModel)
            .where(*filters)
            .order_by(InvoiceScanModel.created_at.desc())
            .offset(page.offset)
            .limit(page.limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return PaginatedResult(
            items=[invoice_scan_to_domain(row) for row in rows], total=total, page=page
        )

    async def add(self, scan: InvoiceScan) -> InvoiceScan:
        model = InvoiceScanModel(
            id=scan.id,
            company_id=scan.company_id,
            file_id=scan.file_id,
            filename=scan.filename,
            status=scan.status,
            supplier_name=scan.supplier_name,
            supplier_tax_id=scan.supplier_tax_id,
            supplier_id=scan.supplier_id,
            warehouse_id=scan.warehouse_id,
            invoice_number=scan.invoice_number,
            invoice_date=scan.invoice_date,
            currency=scan.currency,
            declared_subtotal=scan.declared_subtotal,
            declared_tax=scan.declared_tax,
            declared_total=scan.declared_total,
            notes=scan.notes,
            extraction=scan.extraction,
            purchase_id=scan.purchase_id,
            created_by=scan.created_by,
            failure_reason=scan.failure_reason,
            lines=[_line_model(line, scan.id) for line in scan.lines],
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return invoice_scan_to_domain(model)

    async def save(self, scan: InvoiceScan) -> InvoiceScan:
        """Encabezado y renglones de una revisión.

        Los renglones se reemplazan en bloque: una revisión toca varios a la
        vez y reconciliar fila por fila solo serviría para dejar un estado
        intermedio raro si algo falla a mitad de camino. Borrar e insertar
        dentro de la misma transacción no tiene ese problema.
        """
        stmt = select(InvoiceScanModel).where(
            InvoiceScanModel.id == scan.id, InvoiceScanModel.company_id == scan.company_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise LookupError(f"Invoice scan {scan.id} disappeared before update")

        model.status = scan.status
        model.supplier_name = scan.supplier_name
        model.supplier_tax_id = scan.supplier_tax_id
        model.supplier_id = scan.supplier_id
        model.warehouse_id = scan.warehouse_id
        model.invoice_number = scan.invoice_number
        model.invoice_date = scan.invoice_date
        model.currency = scan.currency
        model.declared_subtotal = scan.declared_subtotal
        model.declared_tax = scan.declared_tax
        model.declared_total = scan.declared_total
        model.notes = scan.notes
        model.extraction = scan.extraction
        model.purchase_id = scan.purchase_id
        model.failure_reason = scan.failure_reason

        await self._session.execute(
            delete(InvoiceScanLineModel).where(
                InvoiceScanLineModel.scan_id == scan.id,
                InvoiceScanLineModel.company_id == scan.company_id,
            )
        )
        # La colección cargada quedó apuntando a filas que ya no existen;
        # reemplazarla evita que el flush intente borrarlas otra vez.
        model.lines = [_line_model(line, scan.id) for line in scan.lines]
        await self._session.flush()
        await self._session.refresh(model)
        return invoice_scan_to_domain(model)
