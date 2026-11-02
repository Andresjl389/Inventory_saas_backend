"""Punto de composición del lector de facturas.

Mismo criterio que el almacenamiento de archivos: fallar fuerte y temprano. Un
lector mal configurado tiene que doler al arrancar el escaneo, no devolver una
factura vacía que alguien confirme pensando que el papel no traía nada.

Hoy el valor por defecto es "disabled": el escaneo está construido y probado,
pero el modelo espera a que el servidor tenga GPU. Encenderlo es cambiar
`INVOICE_EXTRACTOR=local` y apuntar `INVOICE_LOCAL_URL` al servidor de
inferencia -- ni una línea de código.

El orden de las demás ramas dice la decisión del proyecto: el modelo propio es
el camino, Claude es la vara de medir y el lector de texto es para desarrollo.
"""

from functools import lru_cache

from app.domain.invoices.exceptions import InvoiceScanningDisabledError
from app.domain.invoices.extraction import InvoiceExtractor
from app.infrastructure.invoices.rasterizer import LocalRasterizer
from app.infrastructure.invoices.text_extractor import TextInvoiceExtractor
from app.shared.config.settings import settings


@lru_cache
def get_invoice_extractor() -> InvoiceExtractor:
    if settings.invoice_extractor == "disabled":
        # Se resuelve como dependencia, antes de que el endpoint corra, así que
        # ni se sube el archivo: nada de fotos huérfanas en el almacenamiento.
        raise InvoiceScanningDisabledError()

    if settings.invoice_extractor == "local":
        from app.infrastructure.invoices.local_extractor import LocalModelInvoiceExtractor

        return LocalModelInvoiceExtractor(
            base_url=settings.invoice_local_url,
            model=settings.invoice_local_model,
            rasterizer=LocalRasterizer(
                max_side=settings.invoice_max_image_side,
                max_pages=settings.invoice_max_pages,
            ),
            timeout=settings.invoice_timeout_seconds,
            api_key=settings.invoice_local_api_key,
            json_mode=settings.invoice_local_json_mode,
        )

    if settings.invoice_extractor == "text":
        return TextInvoiceExtractor()

    if settings.invoice_extractor == "claude":
        if not settings.anthropic_api_key:
            # Falta de configuración, no error del cliente: 500 con el detalle
            # en el log del servidor, igual que el almacenamiento sin adaptador.
            raise RuntimeError(
                "Falta ANTHROPIC_API_KEY. El lector por defecto es el modelo "
                "propio (INVOICE_EXTRACTOR=local); Claude solo se usa para "
                "comparar y necesita `uv sync --extra claude`."
            )
        try:
            from app.infrastructure.invoices.claude_extractor import ClaudeInvoiceExtractor
        except ImportError as exc:
            raise RuntimeError(
                "El SDK de Anthropic no está instalado. Es un extra opcional: "
                "`uv sync --extra claude`."
            ) from exc

        return ClaudeInvoiceExtractor(
            api_key=settings.anthropic_api_key,
            model=settings.invoice_model,
            timeout=settings.invoice_timeout_seconds,
        )

    raise NotImplementedError(
        f"El lector de facturas {settings.invoice_extractor!r} no existe. "
        "Escribe un adaptador de InvoiceExtractor y regístralo aquí."
    )
