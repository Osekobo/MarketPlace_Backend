"""Alembic environment configuration.

Migrations run through a synchronous (psycopg2) engine. The URL is taken from
application settings so there is a single source of truth for credentials.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings

# Importing the models package registers every table on Base.metadata.
from app.db.base import Base
import app.models  # noqa: F401  (side-effect: model registration)

config = context.config

# Inject the runtime database URL (sync driver).
config.set_main_option("sqlalchemy.url", settings.sync_database_uri)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostGIS-managed objects that must never be dropped by autogenerate.
_EXCLUDED_TABLES = {"spatial_ref_sys", "geography_columns", "geometry_columns"}


def include_object(object_, name, type_, reflected, compare_to) -> bool:  # noqa: ANN001
    if type_ == "table" and name in _EXCLUDED_TABLES:
        return False
    # Skip GeoAlchemy2's auto-managed spatial indexes; we manage them explicitly.
    if type_ == "index" and name and name.startswith(("idx_", "ix_")) and reflected:
        return True
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sync_database_uri,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
