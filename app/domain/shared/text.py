"""Comparing text that people wrote by hand.

Three places in this system have the same problem: the column headers of
somebody's spreadsheet, the product names in a catalogue, and the abbreviated
descriptions a supplier prints on an invoice. The same thing is written four
ways -- "ARROZ DIANA 500G", "Arroz Diana 500 g", "arroz diana x500".

Folding and token scoring live here so the importer and the invoice scanner
agree on what "the same" means instead of each inventing its own answer.
"""

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def fold(text: object) -> str:
    """Reduce text to comparable words: no accents, no case, no punctuation."""
    stripped = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return _NON_ALNUM.sub(" ", stripped.lower()).strip()


def tokens(text: object) -> set[str]:
    folded = fold(text)
    return set(folded.split()) if folded else set()


def containment(candidate: set[str], subject: set[str]) -> float:
    """How well a candidate's words sit inside a subject's, by whole words.

    A plain substring test is too generous: "costo" is inside "centro de costo
    interno", which is not a cost column, and "agua" is inside "aguardiente".
    Scoring by whole words and penalising the words the subject adds keeps
    "precio venta" matching "precio de venta unitario" while rejecting those.
    """
    if not candidate or not subject:
        return 0.0
    shared = candidate & subject
    if not shared:
        return 0.0
    coverage = len(shared) / len(candidate)
    extra = len(subject - candidate) / len(subject)
    return coverage * (1 - 0.5 * extra)
