"""Alembic migration environment.

Configured for async SQLAlchemy (asyncpg). The DATABASE_URL env var
overrides the static URL in alembic.ini so that CI and containers
can inject the correct connection string without editing config files.

IMPORTANT: Application startup must NOT call Base.metadata.create_all().
All schema changes go through Alembic migrations only.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so that their tables are registered on Base.metadata
# before Alembic generates the autogenerate diff.
from app.core.config import Settings
from app.models.complaint import Base  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The URL comes only from the environment: DATABASE_URL if exported (CI,
# Docker, K8s), otherwise the app's settings, which also read .env. No URL,
# and no password, ever lives in alembic.ini.
db_url = os.getenv("DATABASE_URL") or str(Settings().database_url)
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode.

    This configures the context with just a URL and not an Engine.
    By skipping the Engine creation we don't even need a DBAPI to be available.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine (asyncpg)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in online mode (normal operation)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
