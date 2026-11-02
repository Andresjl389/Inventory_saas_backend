"""Matching the columns of somebody's spreadsheet to our fields.

This is the step that makes an import feel like Power Query: the file is read,
its headers become labels, and each one is proposed against a target field with
a confidence. The user confirms or corrects; nothing is guessed silently at
load time.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.domain.imports.schemas import EntitySchema
from app.domain.shared.text import containment, fold

# Below this, a guess is worse than no guess: the column is left unmapped and
# the user picks from the list.
MIN_CONFIDENCE = 0.72

# Above this the match is an exact name or close to it. Between the two, the
# suggestion is usable but worth a glance -- "centro de costo" looks a lot like
# a cost column and is not one. The mapping screen marks these for review.
CONFIDENT = 0.9


def normalise_header(text: str) -> str:
    """Fold a header to something comparable: no accents, no case, no noise."""
    return fold(text)


@dataclass(frozen=True, slots=True)
class ColumnSuggestion:
    source: str
    target: str | None
    confidence: float
    reason: str

    @property
    def needs_review(self) -> bool:
        return self.target is not None and self.confidence < CONFIDENT


def _candidates(schema: EntitySchema) -> list[tuple[str, str]]:
    """(normalised text, target key) for every name a field answers to."""
    pairs: list[tuple[str, str]] = []
    for spec in schema.fields:
        pairs.append((normalise_header(spec.key), spec.key))
        pairs.append((normalise_header(spec.label), spec.key))
        pairs.extend((normalise_header(alias), spec.key) for alias in spec.aliases)
    return pairs


def suggest_mapping(headers: list[str], schema: EntitySchema) -> list[ColumnSuggestion]:
    """Propose a target for each column, best matches first.

    A target is only ever proposed once: two columns that both look like
    "precio" cannot silently both map to sale_price, which would make the
    import depend on column order.
    """
    candidates = _candidates(schema)
    scored: list[tuple[float, int, str, str, str]] = []

    for index, header in enumerate(headers):
        normalised = normalise_header(header)
        if not normalised:
            continue

        header_tokens = set(normalised.split())

        best_key, best_score, best_reason = None, 0.0, ""
        for candidate, key in candidates:
            if not candidate:
                continue
            if candidate == normalised:
                score, reason = 1.0, "exact"
            else:
                inside = containment(set(candidate.split()), header_tokens)
                similarity = SequenceMatcher(None, normalised, candidate).ratio()
                score, reason = (
                    (inside, "contains") if inside >= similarity else (similarity, "similar")
                )
            if score > best_score:
                best_key, best_score, best_reason = key, score, reason

        if best_key and best_score >= MIN_CONFIDENCE:
            scored.append((best_score, index, header, best_key, best_reason))

    taken: set[str] = set()
    resolved: dict[int, ColumnSuggestion] = {}
    for score, index, header, key, reason in sorted(scored, key=lambda item: -item[0]):
        if key in taken:
            continue
        taken.add(key)
        resolved[index] = ColumnSuggestion(
            source=header, target=key, confidence=round(score, 3), reason=reason
        )

    return [
        resolved.get(
            index,
            ColumnSuggestion(source=header, target=None, confidence=0.0, reason="unmatched"),
        )
        for index, header in enumerate(headers)
    ]


def missing_required(mapping: dict[str, str], schema: EntitySchema) -> list[str]:
    """Required target fields no column feeds."""
    mapped = set(mapping.values())
    return [key for key in schema.required_keys if key not in mapped]
