#!/usr/bin/env python3
"""
Migration recovery utility.

Run this when `alembic upgrade head` fails with:
  "current transaction is aborted, commands ignored"

It applies every schema change safely using:
  - autocommit=True  (each statement is independent)
  - ADD COLUMN IF NOT EXISTS  (never fails on duplicates)
  - Then stamps alembic_version correctly

Usage:
  python scripts/fix_migration.py
  python scripts/fix_migration.py --target 002_upgrade
"""
import sys
import os
import argparse
import logging
from pathlib import Path

_ROOT    = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
sys.path.insert(0, str(_BACKEND))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("fix_migration")


# Full list of every column that should exist after migration 002
_ALL_COLUMNS = [
    # (table, column, pg_type)
    ("companies",            "meta_cached_at",         "TIMESTAMPTZ"),
    ("companies",            "updated_at",              "TIMESTAMPTZ DEFAULT now()"),
    ("market_prices",        "dividend_yield",          "NUMERIC(10,6)"),
    ("market_prices",        "updated_at",              "TIMESTAMPTZ DEFAULT now()"),
    ("financial_statements", "filing_form",             "VARCHAR(20)"),
    ("financial_statements", "fiscal_year",             "INTEGER"),
    ("financial_statements", "fiscal_quarter",          "VARCHAR(5)"),
    ("financial_statements", "period_end_date",         "VARCHAR(20)"),
    ("financial_statements", "revenue_prior",           "BIGINT"),
    ("financial_statements", "free_cash_flow",          "BIGINT"),
    ("financial_statements", "updated_at",              "TIMESTAMPTZ DEFAULT now()"),
    ("calculated_multiples", "fcf_yield",               "NUMERIC(20,4)"),
    ("calculated_multiples", "revenue_growth",          "NUMERIC(20,4)"),
    ("calculated_multiples", "gross_margin",            "NUMERIC(20,4)"),
    ("calculated_multiples", "dividend_yield",          "NUMERIC(10,6)"),
    ("calculated_multiples", "eps_growth",              "NUMERIC(20,4)"),
    ("calculated_multiples", "updated_at",              "TIMESTAMPTZ DEFAULT now()"),
    ("peer_statistics",      "median_fcf_yield",        "NUMERIC(20,4)"),
    ("peer_statistics",      "median_revenue_growth",   "NUMERIC(20,4)"),
    ("peer_statistics",      "median_gross_margin",     "NUMERIC(20,4)"),
    ("peer_statistics",      "mean_fcf_yield",          "NUMERIC(20,4)"),
    ("peer_statistics",      "mean_revenue_growth",     "NUMERIC(20,4)"),
    ("peer_statistics",      "mean_gross_margin",       "NUMERIC(20,4)"),
    ("peer_statistics",      "updated_at",              "TIMESTAMPTZ DEFAULT now()"),
]


def parse_args():
    p = argparse.ArgumentParser(description="Migration recovery utility")
    p.add_argument(
        "--target", default="002_upgrade",
        help="Alembic revision to stamp after recovery (default: 002_upgrade)"
    )
    p.add_argument(
        "--check-only", action="store_true",
        help="Only check current state, don't make changes"
    )
    return p.parse_args()


def main():
    args = parse_args()

    from app.core.config import settings
    import psycopg2

    sync_url = settings.SYNC_DATABASE_URL
    logger.info(f"Connecting to: {sync_url.split('@')[-1]}")

    try:
        conn = psycopg2.connect(sync_url)
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        logger.error("Check backend/.env — SYNC_DATABASE_URL must be correct")
        sys.exit(1)

    conn.autocommit = True   # critical — each statement is fully independent
    cur = conn.cursor()

    if args.check_only:
        logger.info("Check-only mode — reporting current state")
        for table, col, _ in _ALL_COLUMNS:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name=%s AND column_name=%s
            """, (table, col))
            exists = cur.fetchone() is not None
            status = "✓ exists" if exists else "✗ MISSING"
            logger.info(f"  {status}  {table}.{col}")
        cur.close()
        conn.close()
        return

    # ── Ensure alembic_version table exists ───────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alembic_version (
            version_num VARCHAR(32) NOT NULL PRIMARY KEY
        )
    """)
    logger.info("alembic_version table ensured")

    # ── Apply every ADD COLUMN IF NOT EXISTS ──────────────────────────
    ok = skip = fail = 0
    for table, col, col_type in _ALL_COLUMNS:
        sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"
        try:
            cur.execute(sql)
            logger.info(f"  ✓  {table}.{col}")
            ok += 1
        except Exception as e:
            # Table might not exist yet — that's OK if 001 hasn't run
            logger.warning(f"  ⚠  {table}.{col}: {e}")
            fail += 1

    # ── Stamp Alembic ─────────────────────────────────────────────────
    cur.execute("DELETE FROM alembic_version")
    cur.execute(
        "INSERT INTO alembic_version (version_num) VALUES (%s)",
        (args.target,)
    )
    logger.info(f"Alembic stamped to: {args.target}")

    cur.close()
    conn.close()

    logger.info("")
    logger.info("=" * 55)
    logger.info(f"  Recovery complete — {ok} columns applied, {fail} skipped")
    logger.info("  Next step: python scripts/seed.py --limit 5")
    logger.info("=" * 55)


if __name__ == "__main__":
    main()
