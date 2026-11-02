from app.shared.exceptions import (
    AppError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)


class InvoiceScanningDisabledError(AppError):
    """El escaneo está construido pero sin modelo detrás todavía.

    503 y no 4xx porque el cliente no hizo nada mal: es una capacidad que este
    servidor no tiene encendida. Así el frontend puede apagar el botón en vez
    de mostrarle al tendero un error que parece culpa de su foto.
    """

    code = "INVOICE_SCANNING_DISABLED"
    message = (
        "La lectura de facturas no está habilitada en este servidor todavía. "
        "Se enciende configurando INVOICE_EXTRACTOR."
    )
    status_code = 503


class InvoiceScanNotFoundError(NotFoundError):
    code = "INVOICE_SCAN_NOT_FOUND"
    message = "Ese escaneo de factura no existe"


class ScanNotOpenError(BusinessRuleError):
    code = "SCAN_NOT_OPEN"
    message = "Ese escaneo ya se cerró y no se puede modificar"


class UnsupportedInvoiceFileError(ValidationError):
    code = "UNSUPPORTED_INVOICE_FILE"
    message = "Solo se pueden leer fotos (JPG, PNG, WEBP) y PDF"


class InvoiceExtractionFailedError(BusinessRuleError):
    """La lectura no se pudo hacer: el modelo falló, no respondió o devolvió
    algo que no se parece a una factura."""

    code = "INVOICE_EXTRACTION_FAILED"
    message = "No se pudo leer la factura"


class EmptyInvoiceError(ValidationError):
    code = "EMPTY_INVOICE"
    message = "No se encontró ningún renglón en ese documento"


class UndecidedLinesError(BusinessRuleError):
    """Confirmar un escaneo con renglones sin decidir crearía una compra que
    nadie revisó. Es exactamente el error que el escaneo existe para evitar."""

    code = "UNDECIDED_LINES"
    message = "Hay renglones sin decidir: enlázalos a un producto, créalos o descártalos"


class NothingToPurchaseError(BusinessRuleError):
    code = "NOTHING_TO_PURCHASE"
    message = "Todos los renglones quedaron descartados: no hay nada que comprar"


class WarehouseRequiredError(ValidationError):
    code = "WAREHOUSE_REQUIRED"
    message = "Falta decir a qué bodega entra la mercancía"
