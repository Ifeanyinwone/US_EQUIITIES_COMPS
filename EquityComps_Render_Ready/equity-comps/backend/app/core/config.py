"""
Centralized configuration — single source of truth for all modules.

Load order:
  1. Defaults defined here
  2. backend/.env file (auto-detected regardless of working directory)
  3. Real environment variables (highest priority)

All scripts, Alembic, and the API server use this same module.
"""
import sys
import os
import logging
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator

# ── Locate .env relative to this file, not the working directory ──────────
_BACKEND_DIR = Path(__file__).resolve().parents[2]   # backend/
_ENV_FILE    = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ───────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:password@localhost:5432/equity_comps"
    )
    SYNC_DATABASE_URL: str = (
        "postgresql://postgres:password@localhost:5432/equity_comps"
    )

    # ── CORS ───────────────────────────────────────────────────────────
    CORS_ORIGINS: str = '["http://localhost:3000","http://localhost:5173"]'

    # ── Scheduler ──────────────────────────────────────────────────────
    MARKET_REFRESH_INTERVAL: int = 300    # seconds
    FINANCIALS_REFRESH_HOUR: int = 2      # UTC hour for nightly refresh

    # ── Logging ────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── Yahoo Finance throttle ─────────────────────────────────────────
    YF_REQUEST_DELAY:    float = 1.5    # seconds between individual requests
    YF_BATCH_DELAY:      float = 3.0    # seconds between batch downloads
    YF_MAX_RETRIES:      int   = 3
    YF_CONCURRENCY:      int   = 2      # max parallel yfinance workers
    YF_COOLDOWN_PERIOD:  float = 30.0   # seconds to wait after a 429

    # ── Seeding ────────────────────────────────────────────────────────
    SEED_PROGRESS_FILE: str = "seed_progress.json"

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError(
                f"DATABASE_URL must start with 'postgresql', got: {v!r}\n"
                "  Fix: edit backend/.env and set DATABASE_URL correctly."
            )
        return v

    @field_validator("SYNC_DATABASE_URL")
    @classmethod
    def validate_sync_db_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError(
                f"SYNC_DATABASE_URL must start with 'postgresql', got: {v!r}\n"
                "  Fix: edit backend/.env and set SYNC_DATABASE_URL correctly."
            )
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        import json
        try:
            return json.loads(self.CORS_ORIGINS)
        except Exception:
            return ["http://localhost:3000"]

    @property
    def env_file_path(self) -> Path:
        return _ENV_FILE


def _check_python_version() -> None:
    if sys.version_info < (3, 11):
        print(
            f"WARNING: Python {sys.version_info.major}.{sys.version_info.minor} detected. "
            "This project targets Python 3.12+. Some features may not work correctly.",
            file=sys.stderr,
        )


_check_python_version()

try:
    settings = Settings()
except Exception as exc:
    print(f"\n{'='*60}", file=sys.stderr)
    print("CONFIGURATION ERROR — Cannot start EquityComps", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"\n{exc}", file=sys.stderr)
    print(f"\nExpected .env file at: {_ENV_FILE}", file=sys.stderr)
    print("Run: cp backend/.env.example backend/.env", file=sys.stderr)
    print("Then edit backend/.env with your PostgreSQL password.\n", file=sys.stderr)
    sys.exit(1)
