"""Leer la factura con el modelo propio, en nuestro servidor.

Habla el dialecto OpenAI (`POST /v1/chat/completions`), que es el que exponen
vLLM, llama.cpp, Ollama, TGI y LM Studio. Eso es deliberado: el adaptador no
sabe qué modelo hay detrás ni en qué GPU corre, así que cambiar de Qwen2.5-VL a
lo que venga el año entrante -- o a un modelo afinado con nuestras propias
facturas -- es cambiar una variable de entorno, no código.

Tres cosas que hacen la diferencia entre que esto sirva y que no, y ninguna es
el modelo:

* **Decodificación guiada.** Con el esquema JSON forzado, un modelo de 7B deja
  de inventar campos. Sin eso, el mismo modelo falla una de cada tres facturas
  por formato, no por lectura.
* **Temperatura 0.** Leer no es escribir: la misma factura tiene que dar el
  mismo resultado dos veces, o la revisión deja de ser auditable.
* **Imágenes acotadas.** El rasterizador ya recortó al lado largo. En tu propia
  GPU eso no es un ahorro de factura, es la diferencia entre dos segundos y
  diez por documento.
"""

import base64
import json
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.domain.invoices.exceptions import (
    InvoiceExtractionFailedError,
    UnsupportedInvoiceFileError,
)
from app.domain.invoices.extraction import ExtractedInvoice, InvoiceExtractor
from app.domain.invoices.rendering import DocumentRasterizer
from app.infrastructure.invoices.prompting import (
    MAX_OUTPUT_TOKENS,
    PROMPT,
    SYSTEM,
    InvoicePayload,
    json_schema,
    to_extracted,
)

JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LocalModelInvoiceExtractor(InvoiceExtractor):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        rasterizer: DocumentRasterizer,
        timeout: float = 180.0,
        api_key: str | None = None,
        json_mode: str = "json_schema",
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._rasterizer = rasterizer
        self._timeout = timeout
        self._api_key = api_key
        self._json_mode = json_mode
        self._max_output_tokens = max_output_tokens
        # El cliente se puede inyectar para probar sin red.
        self._client = client

    @property
    def source(self) -> str:
        return f"local:{self._model}"

    async def extract(
        self, payload: bytes, content_type: str, filename: str = ""
    ) -> ExtractedInvoice:
        if not self._rasterizer.supports(content_type):
            raise UnsupportedInvoiceFileError(
                f"{content_type or 'desconocido'} no se puede leer como factura"
            )

        pages = self._rasterizer.render(payload, content_type)
        if not pages:
            raise UnsupportedInvoiceFileError("Ese documento no tiene páginas que leer")

        body = self._body(pages)
        data = await self._post(body)
        return to_extracted(self._parse(data), source=self.source)

    def _body(self, pages) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "image_url",
                "image_url": {
                    "url": (
                        f"data:{page.content_type};base64,"
                        f"{base64.standard_b64encode(page.payload).decode()}"
                    )
                },
            }
            for page in pages
        ]
        content.append({"type": "text", "text": self._instruction(len(pages))})

        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": content},
            ],
            # Leer tiene una sola respuesta correcta.
            "temperature": 0,
            "max_tokens": self._max_output_tokens,
            "stream": False,
        }

        if self._json_mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "factura", "schema": json_schema(), "strict": True},
            }
            # vLLM antiguo ignora response_format y mira este campo; mandar los
            # dos no molesta a ninguno de los dos.
            body["guided_json"] = json_schema()
        elif self._json_mode == "json_object":
            body["response_format"] = {"type": "json_object"}

        return body

    def _instruction(self, page_count: int) -> str:
        parts = [PROMPT]
        if page_count > 1:
            parts.append(
                f"El documento tiene {page_count} páginas: son una sola factura, "
                "devuelve los renglones de todas juntos y sin repetir."
            )
        if self._json_mode != "json_schema":
            # Sin gramática forzada, el esquema va en el prompt o el modelo
            # improvisa la forma.
            parts.append(
                "Responde únicamente con un objeto JSON que cumpla este esquema, "
                "sin texto alrededor y sin ```:\n" + json.dumps(json_schema(), ensure_ascii=False)
            )
        return "\n\n".join(parts)

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        url = f"{self._base_url}/chat/completions"
        try:
            if self._client is not None:
                response = await self._client.post(url, json=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise InvoiceExtractionFailedError(
                "El servidor de lectura no respondió a tiempo; vuelve a intentar",
                details={"timeout_seconds": self._timeout},
            ) from exc
        except httpx.HTTPError as exc:
            # El caso más común en producción: el servicio del modelo está
            # caído. Decirlo así evita media hora buscando el error en la foto.
            raise InvoiceExtractionFailedError(
                "No se pudo contactar el servidor de lectura",
                details={"url": url},
            ) from exc

        if response.status_code >= 400:
            raise InvoiceExtractionFailedError(
                "El servidor de lectura rechazó la petición",
                details={"status": response.status_code, "body": response.text[:500]},
            )

        try:
            return response.json()
        except ValueError as exc:
            raise InvoiceExtractionFailedError(
                "El servidor de lectura devolvió algo que no es JSON"
            ) from exc

    def _parse(self, data: dict[str, Any]) -> InvoicePayload:
        choices = data.get("choices") or []
        if not choices:
            raise InvoiceExtractionFailedError("El modelo no devolvió ninguna respuesta")

        choice = choices[0]
        if choice.get("finish_reason") == "length":
            raise InvoiceExtractionFailedError(
                "La respuesta del modelo se cortó por longitud; es una factura "
                "demasiado larga para leerla de una sola vez"
            )

        text = (choice.get("message") or {}).get("content") or ""
        if isinstance(text, list):
            # Algunos servidores devuelven el contenido por bloques.
            text = "".join(block.get("text", "") for block in text if isinstance(block, dict))
        if not text.strip():
            raise InvoiceExtractionFailedError("El modelo devolvió una respuesta vacía")

        try:
            return InvoicePayload.model_validate_json(_json_object(text))
        except (ValidationError, ValueError) as exc:
            raise InvoiceExtractionFailedError(
                "El modelo no devolvió la factura en el formato esperado",
                details={"preview": text[:300]},
            ) from exc


def _json_object(text: str) -> str:
    """El objeto JSON que venga dentro de la respuesta.

    Con gramática forzada el texto ya es JSON puro. Sin ella, un modelo chico
    lo envuelve en ```json o le pone una frase amable antes, y recuperar el
    objeto es más barato que perder la lectura.
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped

    fenced = JSON_FENCE.search(stripped)
    if fenced:
        return fenced.group(1).strip()

    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no hay un objeto JSON en la respuesta")
    return stripped[start : end + 1]
