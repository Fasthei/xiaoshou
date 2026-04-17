"""Alembic env.py — wires alembic to the app's SQLAlchemy Base + DATABASE_URL.

Runs both offline (emit SQL) and online (execute against DB) modes.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import app metadata so autogenerate picks up models.
from app.database import Base  # noqa: E402
from app import models  # noqa: F401,E402  registers all tables on Base.metadata

config = context.config

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        # logging config is optional; don't fail migrations over it
        pass

target_metadata = Base.metadata


def _get_url() -> str:
    """Prefer DATABASE_URL env var, fallback to alembic.ini sqlalchemy.url."""
    url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set and alembic.ini sqlalchemy.url is blank — "
            "cannot run migrations"
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
