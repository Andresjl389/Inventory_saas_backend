"""Test fixtures.

Integration and API tests need a real PostgreSQL: RLS cannot be simulated with
SQLite. Point TEST_DATABASE_URL at a throwaway database (`make test-db` creates
one) -- without it those tests are skipped while the unit tests keep running.

Every database fixture builds its own engine and disposes it, so each test owns
its event loop and no connection outlives the loop that created it.
"""

import asyncio
import os
import subprocess
import uuid
from collections.abc import AsyncIterator

import pytest

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://inventory:inventory@localhost:5432/inventory_test",
)

# Settings are read at import time, so the environment must be shaped first.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-secret-value-that-is-long-enough")
os.environ.setdefault("APP_ENV", "testing")

# Truncation order does not matter (CASCADE), but keeping it child-first makes
# the intent readable.
TABLES = ("products", "categories", "company_members", "companies", "users")


def _database_available() -> bool:
    try:
        import asyncpg

        async def ping() -> None:
            dsn = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            connection = await asyncpg.connect(dsn, timeout=3)
            await connection.close()

        asyncio.run(ping())
        return True
    except Exception:
        return False


DB_AVAILABLE = _database_available()

requires_db = pytest.mark.skipif(
    not DB_AVAILABLE, reason=f"PostgreSQL not reachable at {TEST_DATABASE_URL}"
)


@pytest.fixture(scope="session")
def migrated_database() -> None:
    """Bring the test database to head once per session."""
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        capture_output=True,
    )


@pytest.fixture
async def engine(migrated_database) -> AsyncIterator["object"]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    db_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        yield db_engine
    finally:
        # TRUNCATE is not filtered by RLS, which is exactly what cleanup needs.
        async with db_engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        await db_engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator["object"]:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as db_session:
        yield db_session
        await db_session.rollback()


@pytest.fixture
async def client(engine) -> AsyncIterator["object"]:
    """An HTTP client whose requests run against the per-test engine."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.infrastructure.database.session import create_session
    from app.main import create_app

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async def override_session():
        db_session = factory()
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise
        finally:
            await db_session.close()

    app = create_app()
    app.dependency_overrides[create_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"
