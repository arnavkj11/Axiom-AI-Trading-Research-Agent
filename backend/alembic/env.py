"""Alembic runtime environment — wires migrations to Neon's direct connection.

`alembic.context` is a dynamically-populated proxy module, so pylint can't
see its real attributes (config, configure, begin_transaction, ...); the
module-wide `no-member` disable below is standard for Alembic env.py files.
"""

# pylint: disable=no-member

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the `app` package importable regardless of the directory Alembic is
# invoked from. This file is in backend/alembic/.
BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Alembic loads the application package after configuring its runtime path.
# pylint: disable=import-error,wrong-import-position
from app.core.config import settings  # noqa: E402
from app.db.models import Base  # noqa: E402
# pylint: enable=import-error,wrong-import-position

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Migrations always run against Neon's direct connection, never the pooled
# one (PgBouncer's transaction pooling mode is incompatible with the
# session-level state Alembic needs) — see app/core/config.py.
config.set_main_option("sqlalchemy.url", settings.direct_database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Base.metadata is kept complete by app/db/models.py (imports every domain
# model), so autogenerate sees the full schema.
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
