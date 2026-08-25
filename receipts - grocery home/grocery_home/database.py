"""SQLAlchemy engine, sessions and lightweight schema versioning."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import Settings, get_settings


CURRENT_SCHEMA_VERSION = 2


class Base(DeclarativeBase):
    """Declarative base shared by all Grocery Home models."""


class SchemaVersionError(RuntimeError):
    """Raised when the database schema cannot be upgraded safely."""


Migration = Callable[[Connection], None]
_MIGRATIONS: dict[int, Migration] = {}


def register_migration(version: int) -> Callable[[Migration], Migration]:
    """Register a future forward-only migration.

    Version 1 is the metadata bootstrap and therefore has no migration
    callback.  Later versions must be consecutive and idempotent inside the
    transaction supplied by :func:`initialize_schema`.
    """

    if version <= 1:
        raise ValueError("Explicit migrations must target schema version 2 or later")

    def decorator(callback: Migration) -> Migration:
        if version in _MIGRATIONS:
            raise ValueError(f"A migration for version {version} is already registered")
        _MIGRATIONS[version] = callback
        return callback

    return decorator


def _configure_sqlite_connection(
    dbapi_connection: Any,
    _connection_record: Any,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        # WAL improves read/write coexistence for phones polling a LAN server.
        # SQLite ignores/normalizes this for in-memory databases.
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


@dataclass(slots=True)
class Database:
    """An explicit engine/session bundle that is easy to replace in tests."""

    engine: Engine
    session_factory: sessionmaker[Session]

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a transaction, committing on success and rolling back on error."""

        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()


def create_database(
    settings: Settings | None = None,
    *,
    database_url: str | None = None,
    echo: bool = False,
) -> Database:
    """Create an engine without creating or modifying database tables."""

    if database_url is None:
        active_settings = settings or get_settings()
        active_settings.ensure_directories()
        url = active_settings.database_url
    else:
        url = database_url
    engine_options: dict[str, Any] = {
        "future": True,
        "echo": echo,
        "pool_pre_ping": True,
    }

    if url.startswith("sqlite"):
        engine_options["connect_args"] = {"check_same_thread": False}
        if url.endswith(":memory:"):
            engine_options["poolclass"] = StaticPool

    engine = create_engine(url, **engine_options)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _configure_sqlite_connection)

    return Database(
        engine=engine,
        session_factory=sessionmaker(
            bind=engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        ),
    )


def initialize_schema(database: Database) -> int:
    """Create the schema and apply registered forward migrations atomically."""

    # Importing registers every model on Base.metadata, and every migration
    # on the registry, while avoiding a circular import at module load time.
    from . import migrations as _migrations  # noqa: F401
    from .models import SchemaMigration

    Base.metadata.create_all(database.engine)

    with database.session() as session:
        current_version = session.scalar(select(func.max(SchemaMigration.version))) or 0

    if current_version > CURRENT_SCHEMA_VERSION:
        raise SchemaVersionError(
            "Database schema "
            f"{current_version} is newer than supported version {CURRENT_SCHEMA_VERSION}"
        )

    if current_version == 0:
        with database.session() as session:
            session.add(
                SchemaMigration(
                    version=1,
                    description="Initial Grocery Home schema",
                )
            )
        current_version = 1

    for target_version in range(current_version + 1, CURRENT_SCHEMA_VERSION + 1):
        callback = _MIGRATIONS.get(target_version)
        if callback is None:
            raise SchemaVersionError(
                f"No migration registered for schema version {target_version}"
            )
        with database.engine.begin() as connection:
            callback(connection)
            connection.execute(
                SchemaMigration.__table__.insert().values(
                    version=target_version,
                    description=callback.__doc__ or callback.__name__,
                )
            )
        current_version = target_version

    _ensure_default_household(database)
    return current_version


def _ensure_default_household(database: Database) -> None:
    """Guarantee household 1 exists.

    Every household-owned table defaults `household_id` to 1, so that row has
    to be there for the foreign key to hold. It is the household the
    single-household build wrote into, and after migration it is an ordinary
    household like any other.
    """

    from .models import Household

    with database.session() as session:
        if session.get(Household, 1) is not None:
            return
        session.add(Household(id=1, display_name="Our household"))
        session.commit()


def schema_version(database: Database) -> int:
    """Read the latest installed schema version."""

    from .models import SchemaMigration

    with database.session() as session:
        return session.scalar(select(func.max(SchemaMigration.version))) or 0


@lru_cache(maxsize=1)
def get_database() -> Database:
    return create_database()


def clear_database_cache() -> None:
    if get_database.cache_info().currsize:
        get_database().dispose()
    get_database.cache_clear()


def session_dependency() -> Generator[Session, None, None]:
    """FastAPI dependency that scopes one transaction to a request."""

    with get_database().session() as session:
        yield session


__all__ = [
    "Base",
    "CURRENT_SCHEMA_VERSION",
    "Database",
    "SchemaVersionError",
    "clear_database_cache",
    "create_database",
    "get_database",
    "initialize_schema",
    "register_migration",
    "schema_version",
    "session_dependency",
]
