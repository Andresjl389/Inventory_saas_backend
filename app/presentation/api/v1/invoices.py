"""Escaneo de facturas: le tomas una foto al papel del proveedor y entra.

Tres pasos, y solo el último escribe en la empresa:

1. `POST /invoices/scans` sube la foto y devuelve lo que se leyó, con un
   producto propuesto por renglón y la confianza de cada propuesta. No toca
   inventario ni catálogo.
2. `PATCH /invoices/scans/{id}` guarda las decisiones: este renglón es este
   producto, este otro crea uno nuevo, el flete se descarta. Se puede llamar
   varias veces -- una factura de cuarenta renglones se revisa por partes.
3. `POST /invoices/scans/{id}/confirm` crea los productos nuevos y la compra,
   y mueve el inventario por el mismo camino que una compra escrita a mano.

Lo que no hace, a propósito: confirmar solo. Un renglón sin decidir bloquea la
confirmación en vez de entrar con la propuesta del modelo. Una factura mal
leída que nadie revisó es inventario mentiroso, y el inventario mentiroso es
peor que no tener inventario.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi import status as http_status

from app.application.files.services.owner_check import OwnerCheck
from app.application.files.use_cases.file_use_cases import UploadFileUseCase
from app.application.invoices.dto.scan import (
    ConfirmScanCommand,
    ConfirmScanResultDTO,
    InvoiceScanDTO,
    ListScansQuery,
    ReviewScanCommand,
    ScanPageDTO,
)
from app.application.invoices.services.catalog_matcher import CatalogMatcher
from app.application.invoices.services.product_builder import ProductBuilder
from app.application.invoices.services.references import ReferenceCheck
from app.application.invoices.use_cases.scan_use_cases import (
    CancelScanUseCase,
    ConfirmScanUseCase,
    GetScanUseCase,
    ListScansUseCase,
    RematchScanUseCase,
    ReviewScanUseCase,
    ScanInvoiceUseCase,
)
from app.application.purchases.use_cases.purchase_use_cases import CreatePurchaseUseCase
from app.domain.files.entities.stored_file import FileOwnerType
from app.domain.invoices.entities.scan import ScanStatus
from app.domain.shared.pagination import MAX_PAGE_SIZE
from app.domain.tenants.tenant_context import TenantContext
from app.presentation.api.dependencies.repositories import (
    FileRepoDep,
    FileStorageDep,
    InvoiceExtractorDep,
    InvoiceScanRepoDep,
    ProductRepoDep,
    PurchaseRepoDep,
    SaleRepoDep,
    StockServiceDep,
    SupplierRepoDep,
    WarehouseRepoDep,
)
from app.presentation.api.dependencies.tenant import require_permission
from app.shared.config.settings import settings

router = APIRouter(prefix="/invoices", tags=["facturas"])

ReadDep = Annotated[TenantContext, Depends(require_permission("invoices.read"))]
ScanDep = Annotated[TenantContext, Depends(require_permission("invoices.scan"))]

UPLOAD_CHUNK = 64 * 1024


async def _chunks(payload: bytes) -> AsyncIterator[bytes]:
    for start in range(0, len(payload), UPLOAD_CHUNK):
        yield payload[start : start + UPLOAD_CHUNK]


def _matcher(products: ProductRepoDep) -> CatalogMatcher:
    return CatalogMatcher(products, limit=settings.invoice_match_candidates)


@router.post("/scans", response_model=InvoiceScanDTO, status_code=http_status.HTTP_201_CREATED)
async def scan_invoice(
    tenant: ScanDep,
    scans: InvoiceScanRepoDep,
    files: FileRepoDep,
    storage: FileStorageDep,
    extractor: InvoiceExtractorDep,
    products: ProductRepoDep,
    sales: SaleRepoDep,
    purchases: PurchaseRepoDep,
    suppliers: SupplierRepoDep,
    warehouses: WarehouseRepoDep,
    file: Annotated[UploadFile, File(description="Foto o PDF de la factura")],
    warehouse_id: Annotated[uuid.UUID | None, Form()] = None,
) -> InvoiceScanDTO:
    """Subir la factura y leerla.

    La bodega es opcional aquí y obligatoria para confirmar: quien le toma la
    foto en el mostrador no siempre es quien sabe a qué bodega entra.
    """
    # Un byte más que el tope basta para que la subida lo rechace; leer el
    # cuerpo entero dejaría que un archivo de varios GB llegue a memoria antes
    # de que nadie mire el tamaño.
    payload = await file.read(settings.max_upload_size_bytes + 1)

    stored = await UploadFileUseCase(
        files, storage, OwnerCheck(products, sales, purchases)
    ).execute(
        chunks=_chunks(payload),
        filename=file.filename or "factura.jpg",
        content_type=file.content_type or "image/jpeg",
        owner_type=FileOwnerType.INVOICE,
        owner_id=None,
        tenant=tenant,
        url_prefix=settings.api_v1_prefix,
    )

    return await ScanInvoiceUseCase(
        scans,
        extractor,
        _matcher(products),
        suppliers,
        ReferenceCheck(warehouses, suppliers, products),
    ).execute(payload=payload, stored_file=stored, tenant=tenant, warehouse_id=warehouse_id)


@router.get("/scans", response_model=ScanPageDTO)
async def list_scans(
    tenant: ReadDep,
    scans: InvoiceScanRepoDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    status: ScanStatus | None = None,
) -> ScanPageDTO:
    return await ListScansUseCase(scans).execute(
        ListScansQuery(page=page, size=size, status=status), tenant=tenant
    )


@router.get("/scans/{scan_id}", response_model=InvoiceScanDTO)
async def get_scan(
    scan_id: uuid.UUID, tenant: ReadDep, scans: InvoiceScanRepoDep
) -> InvoiceScanDTO:
    """El escaneo con todos sus renglones: es la pantalla de revisión."""
    return await GetScanUseCase(scans).execute(scan_id, tenant=tenant)


@router.patch("/scans/{scan_id}", response_model=InvoiceScanDTO)
async def review_scan(
    scan_id: uuid.UUID,
    command: ReviewScanCommand,
    tenant: ScanDep,
    scans: InvoiceScanRepoDep,
    warehouses: WarehouseRepoDep,
    suppliers: SupplierRepoDep,
    products: ProductRepoDep,
) -> InvoiceScanDTO:
    """Guardar las decisiones. Los renglones que no manden quedan como están."""
    return await ReviewScanUseCase(scans, ReferenceCheck(warehouses, suppliers, products)).execute(
        scan_id, command, tenant=tenant
    )


@router.post("/scans/{scan_id}/rematch", response_model=InvoiceScanDTO)
async def rematch_scan(
    scan_id: uuid.UUID,
    tenant: ScanDep,
    scans: InvoiceScanRepoDep,
    products: ProductRepoDep,
) -> InvoiceScanDTO:
    """Volver a buscar los renglones sin decidir en el catálogo de ahora.

    No vuelve a leer la foto, así que no cuesta nada: es lo que se llama
    después de crear a mano los productos que faltaban.
    """
    return await RematchScanUseCase(scans, _matcher(products)).execute(scan_id, tenant=tenant)


@router.post("/scans/{scan_id}/confirm", response_model=ConfirmScanResultDTO)
async def confirm_scan(
    scan_id: uuid.UUID,
    command: ConfirmScanCommand,
    tenant: ScanDep,
    scans: InvoiceScanRepoDep,
    purchases: PurchaseRepoDep,
    products: ProductRepoDep,
    warehouses: WarehouseRepoDep,
    suppliers: SupplierRepoDep,
    stock_service: StockServiceDep,
) -> ConfirmScanResultDTO:
    """Crear los productos nuevos y la compra.

    Falla si queda algún renglón sin decidir o si no se dijo la bodega, y lo
    hace antes de crear nada.
    """
    return await ConfirmScanUseCase(
        scans,
        CreatePurchaseUseCase(purchases, products, warehouses, suppliers, stock_service),
        ProductBuilder(products),
    ).execute(scan_id, command, tenant=tenant)


@router.post("/scans/{scan_id}/cancel", response_model=InvoiceScanDTO)
async def cancel_scan(
    scan_id: uuid.UUID, tenant: ScanDep, scans: InvoiceScanRepoDep
) -> InvoiceScanDTO:
    """Descartar el escaneo. La foto queda guardada; el papel sigue siendo el
    papel."""
    return await CancelScanUseCase(scans).execute(scan_id, tenant=tenant)
