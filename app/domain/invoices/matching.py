"""Emparejar el renglón de una factura con un producto del catálogo.

El importador hace lo mismo con los encabezados de un archivo; aquí el texto es
peor. El proveedor imprime "ARROZ DIANA X500GR" y en el catálogo dice "Arroz
Diana 500 g", abreviado distinto cada vez y a veces mal escrito. Por eso hay
dos umbrales y no uno:

* `MIN_CONFIDENCE` -- por debajo no se propone nada. Es bajo a propósito: una
  propuesta mala no hace daño porque igual hay que decidirla a mano, y una
  propuesta que no aparece obliga a buscar el producto en toda la lista.
* `AUTO_LINK` -- por encima el renglón queda enlazado solo. Solo llegan ahí el
  código de barras, el SKU y el nombre casi idéntico; todo lo demás lo decide
  una persona.

Un código de barras o un SKU impresos en la factura ganan siempre: son la única
parte del papel que no es ambigua.
"""

import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.domain.shared.text import containment, fold, tokens

MIN_CONFIDENCE = 0.55
AUTO_LINK = 0.9

# Un SKU de una o dos letras aparece dentro de cualquier descripción por pura
# casualidad; exigir cuatro caracteres evita emparejar por accidente.
MIN_CODE_LENGTH = 4


@dataclass(frozen=True, slots=True)
class ProductCandidate:
    """Lo mínimo del catálogo que sirve para emparejar."""

    product_id: uuid.UUID
    name: str
    sku: str
    barcode: str | None = None


@dataclass(frozen=True, slots=True)
class ProductMatch:
    product_id: uuid.UUID | None
    confidence: float
    reason: str

    @property
    def is_certain(self) -> bool:
        """Suficiente para enlazar sin preguntar."""
        return self.product_id is not None and self.confidence >= AUTO_LINK


UNMATCHED = ProductMatch(product_id=None, confidence=0.0, reason="unmatched")


def _digits(value: str | None) -> str:
    return "".join(character for character in (value or "") if character.isdigit())


def _by_code(code: str, candidates: list[ProductCandidate]) -> ProductMatch | None:
    """El código impreso en la factura, contra códigos de barras y SKU."""
    if len(code.strip()) < MIN_CODE_LENGTH:
        return None

    printed_digits = _digits(code)
    printed = fold(code)

    for candidate in candidates:
        if printed_digits and printed_digits == _digits(candidate.barcode):
            return ProductMatch(product_id=candidate.product_id, confidence=1.0, reason="barcode")
    for candidate in candidates:
        if printed and printed == fold(candidate.sku):
            return ProductMatch(product_id=candidate.product_id, confidence=1.0, reason="sku")
    return None


def _score(candidate: ProductCandidate, description: str, words: set[str]) -> tuple[float, str]:
    name = fold(candidate.name)
    if not name:
        return 0.0, "unmatched"
    if name == description:
        return 1.0, "exact"

    barcode = _digits(candidate.barcode)
    if barcode and len(barcode) >= MIN_CODE_LENGTH and barcode in words:
        return 0.98, "barcode"

    sku = fold(candidate.sku)
    if len(sku) >= MIN_CODE_LENGTH and sku in words:
        return 0.95, "sku"

    inside = containment(set(name.split()), words)
    similarity = SequenceMatcher(None, description, name).ratio()
    return (inside, "contains") if inside >= similarity else (similarity, "similar")


def match_product(
    description: str, candidates: list[ProductCandidate], *, code: str | None = None
) -> ProductMatch:
    """La mejor propuesta para una descripción, o `UNMATCHED`.

    Ante dos candidatos con el mismo puntaje gana el de id menor, no el que
    venga primero en la lista: dos escaneos del mismo papel deben proponer lo
    mismo aunque el catálogo se haya reordenado.
    """
    if code:
        exact = _by_code(code, candidates)
        if exact is not None:
            return exact

    folded = fold(description)
    if not folded:
        return UNMATCHED
    words = tokens(folded)

    best = UNMATCHED
    for candidate in sorted(candidates, key=lambda item: str(item.product_id)):
        score, reason = _score(candidate, folded, words)
        if score > best.confidence:
            best = ProductMatch(
                product_id=candidate.product_id, confidence=round(score, 3), reason=reason
            )

    return best if best.confidence >= MIN_CONFIDENCE else UNMATCHED
