"""Block until the database schema is at the revision this code expects.

Used as the backend's initContainer in Kubernetes: migrations run once, in the
``migrate`` Job, and every backend pod waits here until that Job has brought
the schema to this image's Alembic head. A pod therefore never serves traffic
against a missing or older schema, and replicas never race to migrate.

Usage:
  python -m scripts.wait_for_schema [--timeout 300]

Exit codes: 0 when the schema is at head; 1 on timeout.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def expected_head() -> str:
    """The newest migration revision shipped with this code."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("no Alembic migrations found")
    return head


async def current_revision(database_url: str) -> str | None:
    """The revision recorded in the database, or None if it isn't reachable or migrated yet."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one_or_none()
    except Exception:  # noqa: BLE001 — not reachable, or the table doesn't exist yet: keep waiting
        return None
    finally:
        await engine.dispose()


async def wait(database_url: str, timeout: float, interval: float = 2.0) -> bool:
    head = expected_head()
    deadline = time.monotonic() + timeout
    while True:
        revision = await current_revision(database_url)
        if revision == head:
            print(f"schema is at {head}", flush=True)
            return True
        if time.monotonic() >= deadline:
            print(f"timed out: schema is at {revision!r}, expected {head}", file=sys.stderr, flush=True)
            return False
        print(f"waiting for schema {head} (currently {revision!r})", flush=True)
        await asyncio.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1
    return 0 if asyncio.run(wait(database_url, args.timeout)) else 1


if __name__ == "__main__":
    sys.exit(main())
