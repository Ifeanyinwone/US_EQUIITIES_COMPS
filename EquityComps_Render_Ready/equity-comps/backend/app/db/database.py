"""
Database engine and session factory.
Validates PostgreSQL connectivity at startup with a clear error message.
"""
import sys
import logging
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_engine():
    url = settings.DATABASE_URL
    # Ensure async driver
    if "postgresql://" in url and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"server_settings": {"application_name": "equity_comps"}},
    )


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def verify_db_connection() -> bool:
    """
    Test the database connection at startup.
    Returns True on success, prints a helpful error and exits on failure.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
        return True
    except Exception as exc:
        msg = str(exc)
        print(f"\n{'='*60}", file=sys.stderr)
        print("DATABASE CONNECTION FAILED", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"\nURL: {settings.DATABASE_URL}", file=sys.stderr)
        print(f"Error: {msg}\n", file=sys.stderr)

        if "password" in msg.lower() or "authentication" in msg.lower():
            print("FIX: Wrong password in backend/.env", file=sys.stderr)
            print("     Update DATABASE_URL and SYNC_DATABASE_URL\n", file=sys.stderr)
        elif "does not exist" in msg.lower():
            print("FIX: Database 'equity_comps' doesn't exist.", file=sys.stderr)
            print("     Run: createdb equity_comps", file=sys.stderr)
            print("     Or in psql: CREATE DATABASE equity_comps;\n", file=sys.stderr)
        elif "connection refused" in msg.lower() or "connect" in msg.lower():
            print("FIX: PostgreSQL is not running.", file=sys.stderr)
            print("     macOS:  brew services start postgresql@16", file=sys.stderr)
            print("     Ubuntu: sudo service postgresql start", file=sys.stderr)
            print("     Windows: Start 'postgresql-x64-16' in Services\n", file=sys.stderr)

        return False
