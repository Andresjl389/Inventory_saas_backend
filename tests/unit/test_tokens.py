import pytest

from app.domain.shared.entities import new_id
from app.shared.exceptions import UnauthorizedError
from app.shared.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_access_token_round_trip():
    user_id = new_id()
    payload = decode_token(create_access_token(user_id), expected_type="access")
    assert payload.user_id == user_id


def test_refresh_token_is_rejected_where_an_access_token_is_expected():
    token = create_refresh_token(new_id())
    with pytest.raises(UnauthorizedError):
        decode_token(token, expected_type="access")


def test_tampered_token_is_rejected():
    token = create_access_token(new_id())
    with pytest.raises(UnauthorizedError):
        decode_token(token + "x", expected_type="access")


def test_password_hash_is_salted_and_verifiable():
    first, second = hash_password("s3cret-password"), hash_password("s3cret-password")
    assert first != second
    assert verify_password("s3cret-password", first)
    assert not verify_password("wrong", first)
