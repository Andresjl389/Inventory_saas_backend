"""Rasterizador local: Pillow para fotos, pdfium para PDF.

Las dos operaciones que hace son las que más mueven la aguja en un servidor
propio, y ninguna tiene que ver con el modelo:

* **Rotar según EXIF.** Una foto de celular viene derecha en la galería y
  acostada en los bytes. Un modelo leyendo una factura girada 90 grados se
  equivoca en todo, y es gratis arreglarlo.
* **Reducir al lado largo.** El costo de un modelo de visión es por píxel. 1600
  px de lado largo deja legible el texto de una factura y recorta el trabajo a
  una fracción.
"""

import io

from app.domain.invoices.exceptions import UnsupportedInvoiceFileError
from app.domain.invoices.rendering import RenderedPage

PDF_TYPE = "application/pdf"
JPEG = "image/jpeg"

# Por encima de esto no se gana legibilidad, solo se gasta GPU.
DEFAULT_MAX_SIDE = 1600
# Una "factura" de más hojas que esto casi siempre es un escaneo equivocado.
DEFAULT_MAX_PAGES = 4
JPEG_QUALITY = 85


class LocalRasterizer:
    def __init__(
        self, *, max_side: int = DEFAULT_MAX_SIDE, max_pages: int = DEFAULT_MAX_PAGES
    ) -> None:
        self._max_side = max_side
        self._max_pages = max_pages

    def supports(self, content_type: str) -> bool:
        return content_type == PDF_TYPE or content_type.startswith("image/")

    def render(self, payload: bytes, content_type: str) -> list[RenderedPage]:
        if content_type == PDF_TYPE:
            return self._from_pdf(payload)
        if content_type.startswith("image/"):
            return [self._from_image(payload, content_type)]
        raise UnsupportedInvoiceFileError(
            f"{content_type or 'desconocido'} no se puede convertir en imagen",
            details={"allowed": ["image/*", PDF_TYPE]},
        )

    def _from_image(self, payload: bytes, content_type: str) -> RenderedPage:
        from PIL import Image, ImageOps

        try:
            with Image.open(io.BytesIO(payload)) as image:
                upright = ImageOps.exif_transpose(image)
                if max(upright.size) <= self._max_side:
                    # Ya es chica: devolver los bytes originales evita una
                    # recompresión que solo quitaría nitidez al texto.
                    return RenderedPage(content_type=content_type, payload=payload)
                return RenderedPage(content_type=JPEG, payload=self._encode(upright))
        except UnsupportedInvoiceFileError:
            raise
        except OSError as exc:
            raise UnsupportedInvoiceFileError(
                "Esa imagen no se pudo abrir; vuelve a tomar la foto"
            ) from exc

    def _from_pdf(self, payload: bytes) -> list[RenderedPage]:
        try:
            import pypdfium2
        except ImportError as exc:  # pragma: no cover - dependencia declarada
            raise UnsupportedInvoiceFileError(
                "Para leer PDF hace falta pypdfium2 en el servidor"
            ) from exc

        pages: list[RenderedPage] = []
        document = pypdfium2.PdfDocument(payload)
        try:
            if len(document) == 0:
                raise UnsupportedInvoiceFileError("Ese PDF no tiene páginas")
            for index in range(min(len(document), self._max_pages)):
                page = document[index]
                # pdfium rasteriza a 72 dpi * scale; el scale se calcula para
                # que el lado largo caiga justo en el tope.
                longest = max(page.get_width(), page.get_height()) or 1
                scale = min(self._max_side / longest, 4.0)
                bitmap = page.render(scale=max(scale, 1.0))
                pages.append(RenderedPage(content_type=JPEG, payload=self._encode(bitmap.to_pil())))
        finally:
            document.close()
        return pages

    def _encode(self, image) -> bytes:
        from PIL import Image

        if max(image.size) > self._max_side:
            image.thumbnail((self._max_side, self._max_side), Image.LANCZOS)
        if image.mode != "RGB":
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buffer.getvalue()
