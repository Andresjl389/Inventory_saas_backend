"""The code catalogue and the seeded table must not drift apart.

`app/domain/authorization/permissions.py` is what the routers name in
`require_permission(...)` and what the migrations seed. If the two separate, an
endpoint starts checking a permission no role can ever hold, and it fails
closed -- silently, for everyone.
"""

from sqlalchemy import text

from app.domain.authorization.permissions import (
    ALL_CODES,
    SYSTEM_ROLE_PERMISSIONS,
    WILDCARD,
)
from tests.conftest import requires_db

pytestmark = requires_db


async def test_the_seeded_permissions_match_the_code_catalogue(session):
    stored = set((await session.execute(text("SELECT code FROM permissions"))).scalars().all())

    assert stored == set(ALL_CODES), (
        "permissions table and app.domain.authorization.permissions disagree; "
        f"only in code: {sorted(ALL_CODES - stored)}, only in the database: "
        f"{sorted(stored - ALL_CODES)}"
    )


async def test_the_system_roles_hold_exactly_what_the_catalogue_says(session):
    rows = (
        await session.execute(
            text(
                """
                SELECT r.code, p.code
                FROM roles r
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE r.company_id IS NULL
                """
            )
        )
    ).all()

    granted: dict[str, set[str]] = {}
    for role_code, permission_code in rows:
        granted.setdefault(role_code, set()).add(permission_code)

    for role, expected in SYSTEM_ROLE_PERMISSIONS.items():
        assert granted.get(role.value, set()) == set(expected), role.value


async def test_only_the_owner_holds_the_wildcard(session):
    holders = (
        (
            await session.execute(
                text(
                    """
                SELECT r.code
                FROM roles r
                JOIN role_permissions rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE r.company_id IS NULL AND p.code = :wildcard
                """
                ),
                {"wildcard": WILDCARD},
            )
        )
        .scalars()
        .all()
    )

    assert holders == ["OWNER"]
