"""Database connection and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for ORM models.

    Provides the metadata container used by SQLAlchemy for table definitions
    and Alembic migration discovery. Models should subclass this.
    """

    pass


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency providing an async database session.

    Yields a session that is automatically closed when the request completes.
    The session is created via context manager to ensure proper cleanup even
    on exceptions.

    Usage in FastAPI:
        @app.get("/items")
        async def list_items(session: AsyncSession = Depends(get_async_session)):
            ...
    """
    async with async_session_factory() as session:
        yield session
