"""Identity documents, shared by companies, customers and suppliers."""

from enum import StrEnum


class DocumentType(StrEnum):
    NIT = "NIT"
    CC = "CC"
    CE = "CE"
    PASSPORT = "PASSPORT"
    RUT = "RUT"
    OTHER = "OTHER"
