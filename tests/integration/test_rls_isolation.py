"""Row Level Security is the last barrier between tenants (BACKEND.md 40).

These tests bypass repositories and use cases on purpose: they talk straight to
PostgreSQL, so a bug in the application layer cannot make them pass.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import requires_db

pytestmark = requires_db


async def _set_company(session, company_id: uuid.UUID | None) -> None:
    await session.execute(
        text("SELECT set_config('app.current_company_id', :v, true)"),
        {"v": str(company_id) if company_id else ""},
    )


async def _set_user(session, user_id: uuid.UUID | None) -> None:
    await session.execute(
        text("SELECT set_config('app.current_user_id', :v, true)"),
        {"v": str(user_id) if user_id else ""},
    )


async def _seed_tenant(session, label: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a user, a company, the owner membership and one product."""
    user_id, company_id, product_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    await session.execute(
        text(
            "INSERT INTO users (id, email, password_hash, first_name, last_name) "
            "VALUES (:id, :email, 'x', :first, 'Test')"
        ),
        {"id": user_id, "email": f"{label}-{user_id.hex[:8]}@example.com", "first": label},
    )

    # Creating a tenant means entering its scope first: the INSERT policies on
    # companies and company_members only accept the active company.
    await _set_user(session, user_id)
    await _set_company(session, company_id)

    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, :name)"),
        {"id": company_id, "name": f"Company {label}"},
    )
    await session.execute(
        text(
            "INSERT INTO company_members (company_id, user_id, role) "
            "VALUES (:company_id, :user_id, 'OWNER')"
        ),
        {"company_id": company_id, "user_id": user_id},
    )
    await session.execute(
        text(
            "INSERT INTO products (id, company_id, name, sku) "
            "VALUES (:id, :company_id, :name, :sku)"
        ),
        {
            "id": product_id,
            "company_id": company_id,
            "name": f"Product {label}",
            "sku": f"SKU-{label}",
        },
    )
    return user_id, company_id, product_id


async def test_tenant_cannot_read_another_tenants_products(session):
    _, company_a, product_a = await _seed_tenant(session, "A")
    _, company_b, product_b = await _seed_tenant(session, "B")

    await _set_company(session, company_a)
    visible = (await session.execute(text("SELECT id FROM products"))).scalars().all()

    assert visible == [product_a]
    assert product_b not in visible


async def test_tenant_cannot_update_another_tenants_products(session):
    _, company_a, _ = await _seed_tenant(session, "A")
    _, _, product_b = await _seed_tenant(session, "B")

    await _set_company(session, company_a)
    result = await session.execute(
        text("UPDATE products SET name = 'hijacked' WHERE id = :id"), {"id": product_b}
    )

    assert result.rowcount == 0


async def test_tenant_cannot_delete_another_tenants_products(session):
    _, company_a, _ = await _seed_tenant(session, "A")
    _, _, product_b = await _seed_tenant(session, "B")

    await _set_company(session, company_a)
    result = await session.execute(text("DELETE FROM products WHERE id = :id"), {"id": product_b})

    assert result.rowcount == 0


async def test_tenant_cannot_insert_rows_owned_by_another_tenant(session):
    _, company_a, _ = await _seed_tenant(session, "A")
    _, company_b, _ = await _seed_tenant(session, "B")

    await _set_company(session, company_a)
    with pytest.raises(DBAPIError) as excinfo:
        await session.execute(
            text(
                "INSERT INTO products (company_id, name, sku) "
                "VALUES (:company_id, 'smuggled', 'SMUGGLED')"
            ),
            {"company_id": company_b},
        )

    assert "row-level security" in str(excinfo.value).lower()


async def test_no_tenant_context_means_no_rows(session):
    await _seed_tenant(session, "A")
    await _seed_tenant(session, "B")

    await _set_company(session, None)
    visible = (await session.execute(text("SELECT id FROM products"))).scalars().all()

    assert visible == []


async def test_user_sees_only_their_own_memberships(session):
    user_a, company_a, _ = await _seed_tenant(session, "A")
    _, company_b, _ = await _seed_tenant(session, "B")

    # The "my companies" screen runs with a user but no company selected.
    await _set_user(session, user_a)
    await _set_company(session, None)
    companies = (await session.execute(text("SELECT id FROM companies"))).scalars().all()

    assert companies == [company_a]
    assert company_b not in companies
