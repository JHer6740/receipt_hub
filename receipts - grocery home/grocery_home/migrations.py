"""Forward-only schema migrations.

Version 2 turns a single-household, shared-PIN database into a multi-tenant
one: it adds accounts and memberships, stamps every household-owned row with
the household it belongs to, and drops the constraint that pinned
``households`` to a single row.

Existing data belongs to household 1, which becomes a normal household.
"""

from __future__ import annotations

from sqlalchemy import Connection, inspect, text

from .database import register_migration

# Tables that gained a household_id. Every one of these is served per-household,
# so a hosted deployment without this column would leak across tenants.
_TENANT_TABLES = (
    "receipts",
    "shopping_items",
    "upload_batches",
    "analytics_snapshots",
)


def _has_column(connection: Connection, table: str, column: str) -> bool:
    inspector = inspect(connection)
    if table not in inspector.get_table_names():
        return False
    return any(row["name"] == column for row in inspector.get_columns(table))


@register_migration(2)
def add_accounts_and_tenancy(connection: Connection) -> None:
    """Add accounts, memberships and per-household ownership."""

    inspector = inspect(connection)
    tables = set(inspector.get_table_names())

    if "users" not in tables:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id VARCHAR(32) NOT NULL PRIMARY KEY,
                    email VARCHAR(320) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    display_name VARCHAR(100) NOT NULL,
                    email_verified_at TIMESTAMP NULL,
                    session_generation INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text("CREATE UNIQUE INDEX uq_users_email ON users (email)")
        )

    if "household_memberships" not in tables:
        connection.execute(
            text(
                """
                CREATE TABLE household_memberships (
                    id VARCHAR(32) NOT NULL PRIMARY KEY,
                    household_id INTEGER NOT NULL
                        REFERENCES households (id) ON DELETE CASCADE,
                    user_id VARCHAR(32) NOT NULL
                        REFERENCES users (id) ON DELETE CASCADE,
                    role VARCHAR(16) NOT NULL DEFAULT 'member',
                    status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    decided_at TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_household_memberships_pair "
                "ON household_memberships (household_id, user_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX ix_household_memberships_user "
                "ON household_memberships (user_id)"
            )
        )

    # Stamp existing rows. Everything already in the database was filed by the
    # one household that could exist, so it belongs to household 1.
    for table in _TENANT_TABLES:
        if table not in tables:
            continue
        if not _has_column(connection, table, "household_id"):
            connection.execute(
                text(
                    f"ALTER TABLE {table} "
                    "ADD COLUMN household_id INTEGER NOT NULL DEFAULT 1"
                )
            )
        connection.execute(
            text(f"UPDATE {table} SET household_id = 1 WHERE household_id IS NULL")
        )

    if not _has_column(connection, "households", "join_code"):
        connection.execute(
            text("ALTER TABLE households ADD COLUMN join_code VARCHAR(16) NULL")
        )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_households_join_code "
            "ON households (join_code)"
        )
    )

    # SQLite cannot drop a CHECK constraint, so the singleton table is rebuilt
    # without it. Doing this last keeps the foreign keys above valid.
    _rebuild_households_without_singleton(connection)


def _rebuild_households_without_singleton(connection: Connection) -> None:
    """Drop `ck_households_singleton` by recreating the table.

    `pin_hash` also becomes nullable: only the legacy shared-PIN household has
    one, and households created through the API never will.
    """

    definition = connection.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name='households'")
    ).scalar()
    if definition is None or "ck_households_singleton" not in definition:
        return

    connection.execute(
        text(
            """
            CREATE TABLE households_rebuilt (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                display_name VARCHAR(100) NOT NULL DEFAULT 'Our household',
                join_code VARCHAR(16) NULL,
                pin_hash VARCHAR(255) NULL,
                session_generation INTEGER NOT NULL DEFAULT 1,
                timezone VARCHAR(64) NOT NULL DEFAULT 'Australia/Sydney',
                currency VARCHAR(3) NOT NULL DEFAULT 'AUD',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO households_rebuilt (
                id, display_name, join_code, pin_hash, session_generation,
                timezone, currency, created_at, updated_at
            )
            SELECT id, display_name, join_code, pin_hash, session_generation,
                   timezone, currency, created_at, updated_at
            FROM households
            """
        )
    )
    connection.execute(text("DROP TABLE households"))
    connection.execute(text("ALTER TABLE households_rebuilt RENAME TO households"))
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_households_join_code "
            "ON households (join_code)"
        )
    )


__all__ = ["add_accounts_and_tenancy"]
