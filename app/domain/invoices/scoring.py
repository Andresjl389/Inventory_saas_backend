"""Medir qué tan bien se leyó una factura.

Esto es lo que vuelve discutible con números la pregunta «¿nuestro modelo ya
está suficientemente bueno?». Sin medir, la respuesta la da la última factura
que alguien recuerda, y esa siempre es la que salió mal.

La materia prima aparece sola: cada escaneo guarda la lectura cruda del modelo
y, al confirmarse, la versión que dejó una persona. Lo primero es lo que el
modelo dijo; lo segundo es la verdad. Comparar los dos sobre el tráfico real es
una evaluación gratis que se actualiza todos los días.

Dos criterios, y la diferencia importa al decidir:

* **Encabezado**: cada campo acierta o no. Un número de factura mal leído se
  corrige en dos segundos.
* **Renglones**: un renglón cuenta como acierto solo si coinciden descripción,
  cantidad y costo. Los que faltan pesan más que los que sobran: un renglón
  inventado salta a la vista en la revisión, uno que falta entra al inventario
  como mercancía que nunca llegó.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.domain.shared.text import fold

HEADER_FIELDS = (
    "supplier_name",
    "supplier_tax_id",
    "invoice_number",
    "invoice_date",
    "total",
)


def _number(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _same_text(left: object, right: object) -> bool:
    return fold(left or "") == fold(right or "")


def _same_number(left: object, right: object) -> bool:
    first, second = _number(left), _number(right)
    if first is None or second is None:
        return first is None and second is None
    return first == second


def _same_field(name: str, left: object, right: object) -> bool:
    if name == "total":
        return _same_number(left, right)
    return _same_text(left, right)


@dataclass(frozen=True, slots=True)
class LineScore:
    exact: int = 0
    # Mismo producto, cifras distintas: la revisión lo arregla rápido.
    partial: int = 0
    # Renglón que el modelo no vio: el error caro.
    missed: int = 0
    # Renglón que el modelo inventó o partió en dos.
    extra: int = 0

    @property
    def expected(self) -> int:
        return self.exact + self.partial + self.missed

    @property
    def accuracy(self) -> float:
        return self.exact / self.expected if self.expected else 1.0


@dataclass(frozen=True, slots=True)
class ReadingScore:
    header: dict[str, bool] = field(default_factory=dict)
    lines: LineScore = field(default_factory=LineScore)

    @property
    def header_accuracy(self) -> float:
        if not self.header:
            return 1.0
        return sum(1 for hit in self.header.values() if hit) / len(self.header)

    @property
    def is_clean(self) -> bool:
        """Lectura que no habría necesitado ni una corrección."""
        return all(self.header.values()) and self.lines.exact == self.lines.expected


def score_header(read: dict, truth: dict) -> dict[str, bool]:
    """Campo por campo, solo los que la factura verdadera traía.

    Un campo que el papel no tenía no se le puede cobrar al modelo.
    """
    return {
        name: _same_field(name, read.get(name), truth.get(name))
        for name in HEADER_FIELDS
        if truth.get(name) not in (None, "")
    }


def score_lines(read: list[dict], truth: list[dict]) -> LineScore:
    """Emparejar por descripción y después mirar las cifras.

    El emparejamiento es por texto normalizado y consume el candidato, así que
    una factura con dos renglones iguales (pasa: dos cajas del mismo producto a
    precios distintos) no cuenta dos veces el mismo acierto.
    """
    pending = list(read)
    exact = partial = missed = 0

    for expected in truth:
        match = None
        for index, candidate in enumerate(pending):
            if _same_text(candidate.get("description"), expected.get("description")):
                match = index
                break
        if match is None:
            missed += 1
            continue

        candidate = pending.pop(match)
        if _same_number(candidate.get("quantity"), expected.get("quantity")) and _same_number(
            candidate.get("unit_cost"), expected.get("unit_cost")
        ):
            exact += 1
        else:
            partial += 1

    return LineScore(exact=exact, partial=partial, missed=missed, extra=len(pending))


def score_reading(read: dict, truth: dict) -> ReadingScore:
    return ReadingScore(
        header=score_header(read, truth),
        lines=score_lines(read.get("lines") or [], truth.get("lines") or []),
    )
