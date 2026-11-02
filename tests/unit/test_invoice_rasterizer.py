"""Convertir el documento en píxeles que el modelo propio pueda leer.

Dos cosas se prueban porque las dos cuestan segundos de GPU o lecturas
equivocadas: que una foto de celular llegue derecha y acotada, y que un PDF de
facturación electrónica se vuelva imágenes.
"""

import io

import pytest
from PIL import Image

from app.domain.invoices.exceptions import UnsupportedInvoiceFileError
from app.infrastructure.invoices.rasterizer import LocalRasterizer

MAX_SIDE = 1600


def photo(width: int, height: int, fmt: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format=fmt)
    return buffer.getvalue()


def pdf(pages: int) -> bytes:
    import pypdfium2

    document = pypdfium2.PdfDocument.new()
    for _ in range(pages):
        document.new_page(595, 842)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_a_phone_photo_is_cut_down_to_the_long_side():
    """12 megapíxeles son cuatro veces el trabajo por la misma lectura."""
    rendered = LocalRasterizer().render(photo(4000, 3000), "image/jpeg")

    assert len(rendered) == 1
    assert max(Image.open(io.BytesIO(rendered[0].payload)).size) == MAX_SIDE
    assert rendered[0].content_type == "image/jpeg"


def test_a_small_image_is_passed_through_untouched():
    """Recomprimir lo que ya es chico solo le quita nitidez al texto."""
    original = photo(800, 600, fmt="PNG")

    rendered = LocalRasterizer().render(original, "image/png")

    assert rendered[0].payload == original
    assert rendered[0].content_type == "image/png"


def test_an_electronic_invoice_pdf_becomes_one_image_per_page():
    rendered = LocalRasterizer().render(pdf(2), "application/pdf")

    assert len(rendered) == 2
    assert all(page.content_type == "image/jpeg" for page in rendered)
    assert max(Image.open(io.BytesIO(rendered[0].payload)).size) == MAX_SIDE


def test_a_pdf_with_too_many_pages_is_cut_at_the_cap():
    """Una 'factura' de veinte hojas casi siempre es un escaneo equivocado."""
    rendered = LocalRasterizer(max_pages=2).render(pdf(5), "application/pdf")

    assert len(rendered) == 2


def test_a_file_that_is_not_a_document_is_refused():
    with pytest.raises(UnsupportedInvoiceFileError):
        LocalRasterizer().render(b"PK\x03\x04", "application/zip")


def test_a_broken_image_is_refused_with_something_actionable():
    with pytest.raises(UnsupportedInvoiceFileError, match="foto"):
        LocalRasterizer().render(b"no soy una imagen", "image/jpeg")


def test_it_knows_what_it_can_render():
    rasterizer = LocalRasterizer()

    assert rasterizer.supports("image/jpeg")
    assert rasterizer.supports("application/pdf")
    assert not rasterizer.supports("text/csv")
