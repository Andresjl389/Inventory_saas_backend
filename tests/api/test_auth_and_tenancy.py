"""End-to-end HTTP flow: register -> login -> pick a company -> use it."""

import uuid

from tests.api.helpers import PASSWORD
from tests.api.helpers import headers as _headers
from tests.api.helpers import login as _login
from tests.api.helpers import register as _register
from tests.conftest import requires_db

pytestmark = requires_db


async def test_register_creates_user_and_bootstraps_owner_company(client, unique_email):
    body = await _register(client, unique_email)

    assert body["user"]["email"] == unique_email
    assert body["company_id"] is not None

    token = await _login(client, unique_email)
    companies = await client.get("/api/v1/companies", headers=_headers(token))

    assert companies.status_code == 200
    assert companies.json()[0]["role"] == "OWNER"


async def test_duplicate_email_is_rejected_with_a_typed_error(client, unique_email):
    await _register(client, unique_email)
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": PASSWORD,
            "first_name": "Ada",
            "last_name": "Lovelace",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


async def test_login_with_a_wrong_password_gives_no_hint(client, unique_email):
    await _register(client, unique_email)
    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "not-the-password"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_protected_endpoint_requires_a_company_header(client, unique_email):
    await _register(client, unique_email)
    token = await _login(client, unique_email)

    response = await client.get("/api/v1/products", headers=_headers(token))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "COMPANY_REQUIRED"


async def test_membership_is_required_for_the_requested_company(client, unique_email):
    await _register(client, unique_email)
    token = await _login(client, unique_email)

    other_company = str(uuid.uuid4())
    response = await client.get("/api/v1/products", headers=_headers(token, other_company))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_MEMBERSHIP"


async def test_refresh_returns_a_new_token_pair(client, unique_email):
    await _register(client, unique_email)
    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": PASSWORD}
    )
    refresh_token = login.json()["refresh_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert response.json()["access_token"]
