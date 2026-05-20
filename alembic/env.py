import asyncio
import logging
from collections.abc import Callable

from alembic import context
from sqlalchemy import Connection

from app.infrastructure.database import get_engine
from app.infrastructure.settings import get_settings

logger = logging.getLogger("alembic.env")


def get_dsn(db_name: str) -> str:
    """Build a postgresql+asyncpg DSN for *db_name* from application Settings."""
    settings = get_settings()
    return (
        f"postgresql+asyncpg://{settings.app_postgres_user}:"
        f"{settings.app_postgres_password}@{settings.app_postgres_host}:"
        f"{settings.app_postgres_port}/{db_name}"
    )


def do_run_migrations(connection: Connection) -> None:
    """Synchronous callback invoked via run_sync inside an async context."""
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline(db_name: str, versions_path: str) -> None:
    """Emit migration SQL to stdout without a live database connection."""
    url = get_dsn(db_name)
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        version_locations=[versions_path],
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online(db_name: str) -> None:
    """Apply migrations against a live database using the project AsyncEngine."""
    engine = get_engine(db_name)

    async def _run() -> None:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)

    asyncio.run(_run())


def run_migrations_for_db(db_name: str, versions_path: str) -> None:
    """Run the migration lineage for *db_name* located at *versions_path*."""
    context.config.set_main_option("version_locations", versions_path)

    if context.is_offline_mode():
        run_migrations_offline(db_name, versions_path)
    else:
        run_migrations_online(db_name)


def run_aton_clients() -> None:
    """Run migrations for the shared registry database."""
    settings = get_settings()
    db_name = settings.alembic_shared_db
    run_migrations_for_db(db_name, "alembic/versions/aton_clients")


def run_client_template() -> None:
    """Run migrations for the per-tenant template database."""
    settings = get_settings()
    db_name = settings.alembic_template_db
    run_migrations_for_db(db_name, "alembic/versions/client_template")


_SECTION_HANDLERS: dict[str, Callable[[], None]] = {
    "aton_clients": run_aton_clients,
    "client_template": run_client_template,
}

section = context.config.config_ini_section
handler = _SECTION_HANDLERS.get(section)

if handler is None:
    raise RuntimeError(
        f"Unknown alembic config section '{section}'. "
        f"Valid sections: {list(_SECTION_HANDLERS)}"
    )

handler()
