"""The platform console: provisioning companies, users, plans and the audit log."""

from tests.api.helpers import (
    as_company,
    create_product,
    headers,
    platform_admin,
    register,
    tenant,
)
from tests.conftest import requires_db

pytestmark = requires_db


async def test_a_normal_user_cannot_reach_the_admin_api(client, engine, unique_email):
    member, _ = await tenant(client, engine, unique_email)

    for path in ("/api/v1/admin/companies", "/api/v1/admin/users", "/api/v1/admin/stats"):
        response = await client.get(path, headers=member)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "NOT_PLATFORM_ADMIN"


async def test_provisioning_creates_the_company_its_owner_and_a_subscription(client, engine):
    admin = await platform_admin(client, engine)

    response = await client.post(
        "/api/v1/admin/companies",
        headers=admin,
        json={
            "name": "Ferreteria Central",
            "owner_email": "dueno@ferreteria.com",
            "owner_password": "owner-password-1",
            "owner_first_name": "Ana",
            "owner_last_name": "Gomez",
            "plan_code": "STANDARD",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["owner_created"] is True
    assert body["company"]["status"] == "ACTIVE"
    assert body["subscription"]["status"] == "TRIALING"

    # The owner can log in with the password the operator set, and is already
    # OWNER of the new company.
    signed_in = await client.post(
        "/api/v1/auth/login",
        json={"email": "dueno@ferreteria.com", "password": "owner-password-1"},
    )
    assert signed_in.status_code == 200, signed_in.text
    companies = await client.get(
        "/api/v1/companies", headers=headers(signed_in.json()["access_token"])
    )
    assert companies.json()[0]["role"] == "OWNER"
    assert companies.json()[0]["company_id"] == body["company"]["id"]


async def test_provisioning_reuses_an_existing_account_as_owner(client, engine, unique_email):
    admin = await platform_admin(client, engine)
    await register(client, unique_email)

    response = await client.post(
        "/api/v1/admin/companies",
        headers=admin,
        json={"name": "Segunda Empresa", "owner_email": unique_email},
    )

    assert response.status_code == 201, response.text
    assert response.json()["owner_created"] is False


async def test_a_new_owner_without_a_password_is_refused(client, engine):
    admin = await platform_admin(client, engine)

    response = await client.post(
        "/api/v1/admin/companies",
        headers=admin,
        json={"name": "Sin Clave", "owner_email": "nadie@example.com"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OWNER_PASSWORD_REQUIRED"


async def test_suspending_a_company_locks_its_members_out(client, engine, unique_email):
    admin = await platform_admin(client, engine)
    member, company_id = await tenant(client, engine, unique_email)
    assert (await client.get("/api/v1/products", headers=member)).status_code == 200

    suspended = await client.patch(
        f"/api/v1/admin/companies/{company_id}", headers=admin, json={"status": "SUSPENDED"}
    )
    assert suspended.json()["status"] == "SUSPENDED"

    blocked = await client.get("/api/v1/products", headers=member)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "INVALID_COMPANY"

    # The operator can still work inside it -- that is usually the point.
    assert (
        await client.get("/api/v1/products", headers=await as_company(admin, company_id))
    ).status_code == 200


async def test_the_admin_sees_every_company_and_a_member_sees_only_theirs(client, engine):
    admin = await platform_admin(client, engine)
    member_a, company_a = await tenant(client, engine, "a@example.com", "Acme")
    await tenant(client, engine, "b@example.com", "Globex")

    listed = await client.get("/api/v1/admin/companies", headers=admin)
    names = {item["name"] for item in listed.json()["items"]}
    assert {"Acme", "Globex"} <= names

    own = await client.get("/api/v1/companies", headers=member_a)
    assert [item["company_id"] for item in own.json()] == [company_a]


async def test_admin_user_management(client, engine):
    admin = await platform_admin(client, engine)

    created = await client.post(
        "/api/v1/admin/users",
        headers=admin,
        json={
            "email": "nuevo@example.com",
            "password": "a-new-password",
            "first_name": "Nuevo",
            "last_name": "Usuario",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    deactivated = await client.patch(
        f"/api/v1/admin/users/{user_id}", headers=admin, json={"is_active": False}
    )
    assert deactivated.json()["is_active"] is False

    denied = await client.post(
        "/api/v1/auth/login",
        json={"email": "nuevo@example.com", "password": "a-new-password"},
    )
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "INACTIVE_USER"


async def test_an_admin_cannot_lock_themselves_out(client, engine):
    admin = await platform_admin(client, engine)
    me = await client.get("/api/v1/auth/me", headers=admin)
    admin_id = me.json()["id"]

    demoted = await client.patch(
        f"/api/v1/admin/users/{admin_id}", headers=admin, json={"is_superuser": False}
    )
    assert demoted.status_code == 422
    assert demoted.json()["error"]["code"] == "CANNOT_DEMOTE_SELF"


async def test_plans_and_subscriptions(client, engine, unique_email):
    admin = await platform_admin(client, engine)
    _, company_id = await tenant(client, engine, unique_email)

    plans = await client.get("/api/v1/admin/plans", headers=admin)
    assert {plan["code"] for plan in plans.json()} >= {"FREE", "STANDARD", "ENTERPRISE"}

    assigned = await client.put(
        f"/api/v1/admin/companies/{company_id}/subscription",
        headers=admin,
        json={"plan_code": "ENTERPRISE", "status": "ACTIVE", "period_days": 365},
    )
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "ACTIVE"

    fetched = await client.get(f"/api/v1/admin/companies/{company_id}/subscription", headers=admin)
    assert fetched.json()["plan_id"] == assigned.json()["plan_id"]


async def test_platform_actions_land_in_the_audit_log(client, engine):
    admin = await platform_admin(client, engine)
    await client.post(
        "/api/v1/admin/companies",
        headers=admin,
        json={
            "name": "Auditada",
            "owner_email": "aud@example.com",
            "owner_password": "owner-password-1",
        },
    )

    log = await client.get(
        "/api/v1/admin/audit", headers=admin, params={"action": "COMPANY_CREATED"}
    )

    assert log.json()["total"] == 1
    entry = log.json()["items"][0]
    assert entry["payload"]["name"] == "Auditada"
    assert entry["payload"]["owner_email"] == "aud@example.com"
    assert "password" not in entry["payload"]


async def test_platform_stats(client, engine, unique_email):
    admin = await platform_admin(client, engine)
    await tenant(client, engine, unique_email)

    stats = (await client.get("/api/v1/admin/stats", headers=admin)).json()

    assert stats["companies_total"] >= 1
    assert stats["platform_admins"] == 1


async def test_an_operator_inside_a_company_still_sees_only_that_company(client, engine):
    """The escape hatch widens the platform tables, never the business ones."""
    admin = await platform_admin(client, engine)
    headers_a, company_a = await tenant(client, engine, "a@example.com", "Acme")
    headers_b, company_b = await tenant(client, engine, "b@example.com", "Globex")
    await create_product(client, headers_a, "ACME-1")
    await create_product(client, headers_b, "GLOBEX-1")

    in_a = await client.get("/api/v1/products", headers=await as_company(admin, company_a))
    in_b = await client.get("/api/v1/products", headers=await as_company(admin, company_b))

    assert [item["sku"] for item in in_a.json()["items"]] == ["ACME-1"]
    assert [item["sku"] for item in in_b.json()["items"]] == ["GLOBEX-1"]
    assert in_a.json()["total"] == 1, "an operator never reads two tenants at once"
