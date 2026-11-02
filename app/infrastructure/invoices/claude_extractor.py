"""Leer la factura con la API de Claude.

Ya no es el camino por defecto -- el modelo propio lo es -- pero se queda por
una razón práctica: es la vara de medir. Cuando haya que decidir si el modelo
propio ya está suficientemente bueno, o si una versión afinada mejoró o
empeoró, la comparación hay que hacerla contra algo, con el mismo prompt y el
mismo esquema (`prompting.py`).

Es opcional: el SDK vive en el extra `claude` y este módulo solo se importa si
`INVOICE_EXTRACTOR=claude`.
"""

import base64

import anthropic

from app.domain.invoices.exceptions import (
    InvoiceExtractionFailedError,
    UnsupportedInvoiceFileError,
)
from app.domain.invoices.extraction import ExtractedInvoice, InvoiceExtractor
from app.infrastructure.invoices.prompting import (
    PROMPT,
    SYSTEM,
    InvoicePayload,
    to_extracted,
)

PDF_TYPE = "application/pdf"
SUPPORTED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")

MAX_TOKENS = 16000


class ClaudeInvoiceExtractor(InvoiceExtractor):
    def __init__(self, *, api_key: str, model: str, timeout: float = 120.0) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)

    @property
    def source(self) -> str:
        return f"claude:{self._model}"

    def _document_block(self, payload: bytes, content_type: str) -> dict:
        encoded = base64.standard_b64encode(payload).decode()
        if content_type in SUPPORTED_IMAGE_TYPES:
            return {
                "type": "image",
                "source": {"type": "base64", "media_type": content_type, "data": encoded},
            }
        if content_type == PDF_TYPE:
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": PDF_TYPE, "data": encoded},
            }
        raise UnsupportedInvoiceFileError(
            f"{content_type or 'desconocido'} no se puede leer como factura",
            details={"allowed": [*SUPPORTED_IMAGE_TYPES, PDF_TYPE]},
        )

    async def extract(
        self, payload: bytes, content_type: str, filename: str = ""
    ) -> ExtractedInvoice:
        content = [self._document_block(payload, content_type), {"type": "text", "text": PROMPT}]

        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": content}],
                output_format=InvoicePayload,
            )
        except anthropic.APIStatusError as exc:
            raise InvoiceExtractionFailedError(
                "El servicio de lectura rechazó la factura",
                details={"status": exc.status_code},
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise InvoiceExtractionFailedError(
                "No se pudo contactar el servicio de lectura; intenta de nuevo"
            ) from exc

        if response.stop_reason == "refusal":
            raise InvoiceExtractionFailedError(
                "El modelo no aceptó leer ese documento",
                details={"reason": getattr(response.stop_details, "category", None)},
            )
        if response.stop_reason == "max_tokens":
            raise InvoiceExtractionFailedError(
                "La factura es demasiado larga para leerla de una sola vez; escanéala por partes"
            )

        parsed = response.parsed_output
        if parsed is None:
            raise InvoiceExtractionFailedError("La lectura no devolvió datos utilizables")

        return to_extracted(parsed, source=self.source)
