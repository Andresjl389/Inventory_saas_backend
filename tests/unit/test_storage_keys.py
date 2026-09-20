"""Key generation and filename sanitisation.

These two functions are the whole defence against a client steering where its
bytes land, so they get their own tests rather than only being exercised
through the API.
"""

import uuid

from app.domain.files.entities.stored_file import FileOwnerType
from app.domain.files.keys import MAX_FILENAME_LENGTH, build_key, safe_filename


def test_the_key_starts_with_the_company_and_ends_with_a_typed_extension():
    company_id = uuid.uuid4()

    key = build_key(
        company_id=company_id, owner_type=FileOwnerType.PRODUCT, content_type="image/png"
    )

    assert key.startswith(f"{company_id}/product/")
    assert key.endswith(".png")


def test_the_extension_comes_from_the_content_type_not_the_filename():
    key = build_key(
        company_id=uuid.uuid4(),
        owner_type=FileOwnerType.COMPANY,
        content_type="application/pdf",
    )
    assert key.endswith(".pdf")


def test_an_unknown_content_type_falls_back_to_a_harmless_extension():
    key = build_key(
        company_id=uuid.uuid4(), owner_type=FileOwnerType.COMPANY, content_type="weird/thing"
    )
    assert key.endswith(".bin")


def test_two_uploads_never_collide():
    args = dict(company_id=uuid.uuid4(), owner_type=FileOwnerType.PRODUCT, content_type="image/png")
    assert build_key(**args) != build_key(**args)


def test_separators_and_traversal_never_survive_a_filename():
    for raw in ("../../etc/passwd", "..\\..\\windows\\system32", "/absolute/path.png"):
        cleaned = safe_filename(raw)
        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert not cleaned.startswith(".")


def test_header_breaking_characters_are_stripped():
    """The name ends up in a Content-Disposition header."""
    cleaned = safe_filename('report";\r\nX-Injected: yes.pdf')

    assert '"' not in cleaned
    assert "\r" not in cleaned and "\n" not in cleaned


def test_a_filename_is_never_empty_and_never_unbounded():
    assert safe_filename("...") == "file"
    assert safe_filename("") == "file"
    assert len(safe_filename("a" * 500)) == MAX_FILENAME_LENGTH


def test_accents_are_transliterated_rather_than_dropped():
    assert safe_filename("cámión-año.png") == "camion-ano.png"
