"""Async engine and session factory."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.shared.config.settings import settings

engine = create_async_engine(
    str(settings.database_url),
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def create_session() -> AsyncIterator[AsyncSession]:
    """One session == one transaction == one request.

    Committing here (rather than inside a use case) keeps the whole request
    atomic, which is what makes `SET LOCAL` tenant scoping correct: the setting
    lives exactly as long as the transaction that reads and writes under it.
    """
    session = SessionFactory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    await engine.dispose()
