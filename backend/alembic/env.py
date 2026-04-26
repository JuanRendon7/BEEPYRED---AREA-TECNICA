"""
Alembic env.py — modo async para asyncpg.

CRITICO: Este archivo debe usar async_engine_from_config porque asyncpg es
un driver async. El env.py sincrono por defecto falla con MissingGreenlet.
Source: Alembic official docs + RESEARCH.md Pattern 1
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Importar todos los modelos para que Alembic detecte las tablas
from app.models import Base  # noqa: F401 — importa todos los modelos via __init__.py
from app.core.config import settings

# Config de alembic
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata de todos los modelos — target para autogenerate
target_metadata = Base.metadata

# Configurar URL desde settings (no desde alembic.ini para no hardcodear credenciales)
config.set_main_option(
    "sqlalchemy.url",
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1),
)


def run_migrations_offline() -> None:
    """Modo offline: genera SQL sin conectar a la DB."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Modo online: conecta a PostgreSQL y aplica migraciones."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda sync_conn: context.configure(
                connection=sync_conn,
                target_metadata=target_metadata,
            )
        )
        async with connection.begin():
            await connection.run_sync(lambda _: context.run_migrations())
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
