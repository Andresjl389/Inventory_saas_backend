"""Volver un documento en páginas de imagen que un modelo de visión pueda ver.

Existe como puerto por dos razones concretas, y las dos cuestan dinero si se
ignoran:

* **Los PDF.** La facturación electrónica llega en PDF, no en foto. Un modelo
  de visión propio recibe píxeles, así que alguien tiene que rasterizar -- y
  ese alguien no debe ser el adaptador del modelo, que mañana cambia.
* **El tamaño.** Una foto de celular son 12 megapíxeles. Un modelo de visión
  cobra (en tokens, y en tu servidor en segundos de GPU) por píxel: mandarla
  completa es pagar cuatro veces por leer lo mismo. Reducirla al lado largo
  justo para que el texto siga legible es la diferencia entre dos segundos y
  diez por factura.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RenderedPage:
    content_type: str
    payload: bytes


class DocumentRasterizer(Protocol):
    def supports(self, content_type: str) -> bool: ...

    def render(self, payload: bytes, content_type: str) -> list[RenderedPage]:
        """Las páginas del documento como imágenes listas para el modelo.

        Una foto da una sola página. Un PDF da una por hoja, hasta el tope que
        el adaptador considere razonable -- una factura de veinte hojas casi
        siempre es un error de escaneo, no una factura.
        """
        ...
