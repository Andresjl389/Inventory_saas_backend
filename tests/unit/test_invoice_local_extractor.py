"""El lector contra nuestro propio servidor de inferencia.

No se prueba el modelo -- eso se mide con facturas reales, no con asserts. Se
prueba el contrato con el servidor: qué se le manda, qué se acepta de vuelta y
qué pasa cuando el servicio está caído, que en producción es el caso más
frecuente.
"""

import io
import json

import httpx
import pytest
from PIL import Image

from app.domain.invoices.exceptions import (
    InvoiceExtractionFailedError,
    UnsupportedInvoiceFileError,
)
from app.infrastructure.invoices.local_extractor import LocalModelInvoiceExtractor
from app.infrastructure.invoices.rasterizer import LocalRasterizer

MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"

ANSWER = {
    "supplier_name": "Distribuidora El Sol",
    "supplier_tax_id": "900.123.456-7",
    "invoice_number": "F-00123",
    "invoice_date": "15/10/2026",
    "currency": "COP",
    "subtotal": None,
    "tax": None,
    "total": "41.000",
    "lines": [
        {
            "description": "ARROZ DIANA X500GR",
            "quantity": "2",
            "unit_cost": "2.500",
            "code": None,
            "unit": None,
            "discount": None,
            "tax": None,
            "total": "5.000",
            "confidence": 1.0,
            "warnings": [],
        }
    ],
    "warnings": [],
}


def photo(width: int = 1200, height: int = 900) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def server(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def reader(handler, **options) -> LocalModelInvoiceExtractor:
    return LocalModelInvoiceExtractor(
        base_url="http://gpu.interno:8000/v1",
        model=MODEL,
        rasterizer=LocalRasterizer(),
        client=server(handler),
        **options,
    )


def replying(content, *, finish_reason: str = "stop", status: int = 200):
    """Un servidor compatible con OpenAI que contesta lo que se le diga."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["headers"] = dict(request.headers)
        if status >= 400:
            return httpx.Response(status, text="boom")
        return httpx.Response(
            status,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": finish_reason,
                    }
                ]
            },
        )

    return handler, captured


async def test_it_reads_the_invoice_our_server_returns():
    handler, _ = replying(json.dumps(ANSWER))

    invoice = await reader(handler).extract(photo(), "image/jpeg", "factura.jpg")

    assert invoice.supplier_name == "Distribuidora El Sol"
    assert invoice.invoice_date.isoformat() == "2026-10-15"
    assert str(invoice.lines[0].unit_cost) == "2500"
    # Deja escrito qué modelo la leyó: sin eso no se pueden comparar versiones.
    assert invoice.source == f"local:{MODEL}"


async def test_it_asks_for_a_deterministic_answer_against_the_json_schema():
    handler, captured = replying(json.dumps(ANSWER))

    await reader(handler).extract(photo(), "image/jpeg")

    body = captured["body"]
    assert captured["url"] == "http://gpu.interno:8000/v1/chat/completions"
    assert body["model"] == MODEL
    # Leer tiene una sola respuesta correcta.
    assert body["temperature"] == 0
    assert body["stream"] is False
    # Forzar el esquema es lo que vuelve usable un modelo de 7B.
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert "guided_json" in body
    # Todas las claves obligatorias: lo ilegible llega como null explícito.
    schema = body["response_format"]["json_schema"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    line = schema["$defs"]["LinePayload"]
    assert set(line["required"]) == set(line["properties"])


async def test_it_sends_the_page_as_an_inline_image_and_nothing_else():
    handler, captured = replying(json.dumps(ANSWER))

    await reader(handler).extract(photo(), "image/jpeg")

    content = captured["body"]["messages"][1]["content"]
    images = [block for block in content if block["type"] == "image_url"]
    assert len(images) == 1
    assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    # No hay llave que mandar: el servidor es nuestro.
    assert "authorization" not in captured["headers"]


async def test_a_private_server_behind_a_key_gets_the_bearer():
    handler, captured = replying(json.dumps(ANSWER))

    await reader(handler, api_key="interno").extract(photo(), "image/jpeg")

    assert captured["headers"]["authorization"] == "Bearer interno"


async def test_a_big_photo_is_cut_down_before_it_costs_gpu():
    handler, captured = replying(json.dumps(ANSWER))

    await reader(handler).extract(photo(4000, 3000), "image/jpeg")

    url = captured["body"]["messages"][1]["content"][0]["image_url"]["url"]
    import base64

    sent = base64.standard_b64decode(url.split(",", 1)[1])
    assert max(Image.open(io.BytesIO(sent)).size) == 1600


async def test_a_multi_page_pdf_goes_as_one_invoice():
    import pypdfium2

    document = pypdfium2.PdfDocument.new()
    document.new_page(595, 842)
    document.new_page(595, 842)
    buffer = io.BytesIO()
    document.save(buffer)

    handler, captured = replying(json.dumps(ANSWER))
    await reader(handler).extract(buffer.getvalue(), "application/pdf")

    content = captured["body"]["messages"][1]["content"]
    assert len([block for block in content if block["type"] == "image_url"]) == 2
    instruction = content[-1]["text"]
    assert "2 páginas" in instruction and "sin repetir" in instruction


async def test_a_small_model_that_wraps_its_json_in_a_fence_is_still_understood():
    """Sin gramática forzada, un modelo chico contesta con ```json."""
    handler, captured = replying(f"Claro, aquí va:\n```json\n{json.dumps(ANSWER)}\n```")

    invoice = await reader(handler, json_mode="json_object").extract(photo(), "image/jpeg")

    assert invoice.invoice_number == "F-00123"
    # Sin gramática, el esquema viaja en el prompt o el modelo improvisa.
    assert "esquema" in captured["body"]["messages"][1]["content"][-1]["text"]
    assert captured["body"]["response_format"] == {"type": "json_object"}


async def test_a_small_model_that_skips_the_keys_it_left_null_does_not_lose_the_invoice():
    """Sin gramática, un modelo chico omite `unit`, `tax`, `code`... en vez de
    mandarlos en null. Lo que sí leyó tiene que llegar."""
    sparse = {
        "supplier_name": "Distribuidora El Sol",
        "total": "41.000",
        "lines": [{"description": "ARROZ DIANA X500GR", "quantity": "2", "unit_cost": "2.500"}],
    }
    handler, _ = replying(f"```json\n{json.dumps(sparse)}\n```")

    invoice = await reader(handler, json_mode="json_object").extract(photo(), "image/jpeg")

    assert invoice.supplier_name == "Distribuidora El Sol"
    assert invoice.invoice_number is None
    assert str(invoice.lines[0].unit_cost) == "2500"
    assert invoice.lines[0].code is None


async def test_numbers_where_strings_were_asked_for_do_not_lose_the_invoice():
    loose = {**ANSWER, "lines": [{**ANSWER["lines"][0], "quantity": 2, "confidence": 95}]}
    handler, _ = replying(json.dumps(loose))

    invoice = await reader(handler).extract(photo(), "image/jpeg")

    assert str(invoice.lines[0].quantity) == "2"
    assert invoice.lines[0].confidence == 0.95


async def test_a_server_that_is_down_says_so_instead_of_blaming_the_photo():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(InvoiceExtractionFailedError, match="contactar el servidor"):
        await reader(handler).extract(photo(), "image/jpeg")


async def test_a_server_that_takes_too_long_says_so():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(InvoiceExtractionFailedError, match="no respondió a tiempo"):
        await reader(handler).extract(photo(), "image/jpeg")


async def test_an_error_from_the_server_carries_its_status():
    handler, _ = replying("", status=500)

    with pytest.raises(InvoiceExtractionFailedError) as error:
        await reader(handler).extract(photo(), "image/jpeg")

    assert error.value.details["status"] == 500


async def test_an_answer_cut_off_by_length_is_not_half_an_invoice():
    """Media factura leída es peor que ninguna: faltarían renglones."""
    handler, _ = replying(json.dumps(ANSWER)[:120], finish_reason="length")

    with pytest.raises(InvoiceExtractionFailedError, match="cortó por longitud"):
        await reader(handler).extract(photo(), "image/jpeg")


async def test_an_answer_that_is_not_an_invoice_is_refused_with_a_preview():
    handler, _ = replying("no entendí la pregunta")

    with pytest.raises(InvoiceExtractionFailedError) as error:
        await reader(handler).extract(photo(), "image/jpeg")

    assert "preview" in error.value.details


async def test_a_file_it_cannot_rasterise_never_reaches_the_model():
    handler, captured = replying(json.dumps(ANSWER))

    with pytest.raises(UnsupportedInvoiceFileError):
        await reader(handler).extract(b"a,b,c", "text/csv")

    assert captured == {}
