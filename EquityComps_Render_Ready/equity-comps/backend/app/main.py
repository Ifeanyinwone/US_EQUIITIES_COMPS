"""
FastAPI application entry point.
Validates DB connectivity at startup before accepting any requests.
"""
import sys
import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.database import engine, verify_db_connection
from app.models.models import Base
from app.api.routes import router

# ── Structured logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────
    logger.info("=" * 55)
    logger.info("  EquityComps API — Starting up")
    logger.info("=" * 55)
    logger.info(f"  Python:   {sys.version.split()[0]}")
    logger.info(f"  Log level: {settings.LOG_LEVEL}")
    logger.info(f"  DB:        {settings.SYNC_DATABASE_URL.split('@')[-1]}")
    logger.info(f"  .env:      {settings.env_file_path}")
    logger.info("=" * 55)

    # 1. Verify DB is reachable
    if not await verify_db_connection():
        logger.error("Cannot start — database connection failed. See errors above.")
        sys.exit(1)

    # 2. Create / update tables (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema verified")

    # Background jobs are intentionally NOT started by the API process.
    # Run the scheduler as a dedicated process.

    logger.info("Startup complete — API is ready")
    yield

    # ── Shutdown ───────────────────────────────────────────────────
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="EquityComps API",
    description="U.S. Equity Comparable Analysis — S&P 500 & Nasdaq-100",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1", tags=["comps"])

@app.get("/health", tags=["system"])
async def health():
    """Health check — also verifies DB connectivity."""
    from sqlalchemy import text
    from app.db.database import AsyncSessionLocal
    db_ok = False
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error(f"Health check DB failure: {e}")

    status = "ok" if db_ok else "degraded"
    return {
        "status":  status,
        "service": "equity-comps-api",
        "version": "2.0.0",
        "db":      "connected" if db_ok else "error",
        "python":  sys.version.split()[0],
    }


# Serve the compiled React application last so API and health routes keep priority.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
