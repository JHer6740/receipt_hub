"""Command-line setup and single-process launcher for Grocery Home."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from sqlalchemy import select

from .analytics import refresh_analytics_snapshot
from .config import ConfigurationError, Settings, sqlite_url
from .database import create_database, initialize_schema
from .importer import ImportSummary, LegacyImportError, import_existing
from .models import Household
from .security import (
    configure_household,
    get_or_create_session_secret,
    validate_pin,
)


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_HOUSEHOLD_NAME = "Our household"


class CommandError(RuntimeError):
    """A user-correctable CLI error that does not need a traceback."""


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _data_directory(value: str) -> Path:
    path = Path(value).expanduser()
    if not str(path).strip():
        raise argparse.ArgumentTypeError("data directory cannot be empty")
    return path


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grocery-home",
        description="Set up and run the private Grocery Home LAN application.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    setup_parser = subcommands.add_parser(
        "setup",
        help="Create the database, household login and initial analytics.",
    )
    setup_parser.add_argument(
        "--data-dir",
        type=_data_directory,
        help=(
            "Runtime data directory. Defaults to "
            "%%LOCALAPPDATA%%\\GroceryHome on Windows."
        ),
    )
    setup_parser.add_argument(
        "--legacy-root",
        type=Path,
        default=_project_root(),
        help=(
            "Project directory containing receipts/ and parsed/. "
            "Defaults to this source checkout."
        ),
    )
    setup_parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Set up an empty household instead of importing the legacy archive.",
    )
    setup_parser.add_argument(
        "--allow-unexpected-counts",
        action="store_true",
        help=(
            "Import even when the archive does not match the locked "
            "103 uploads, 100 canonical receipts, 3 duplicates and 752 items."
        ),
    )
    setup_parser.set_defaults(handler=setup_command)

    serve_parser = subcommands.add_parser(
        "serve",
        help="Run the web app and its durable worker in one process.",
    )
    serve_parser.add_argument(
        "--data-dir",
        type=_data_directory,
        help=(
            "Runtime data directory. Defaults to "
            "%%LOCALAPPDATA%%\\GroceryHome on Windows."
        ),
    )
    serve_parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Address to bind. Defaults to {DEFAULT_HOST} for private LAN access.",
    )
    serve_parser.add_argument(
        "--port",
        type=_port,
        default=DEFAULT_PORT,
        help=f"TCP port to bind. Defaults to {DEFAULT_PORT}.",
    )
    serve_parser.set_defaults(handler=serve_command)
    return parser


def _settings_for(data_dir: Path | None) -> Settings:
    settings = Settings.from_env()
    if data_dir is None:
        return settings
    resolved = data_dir.expanduser().resolve()
    return replace(
        settings,
        data_dir=resolved,
        database_url=sqlite_url(resolved / "grocery_home.sqlite3"),
    )


def _prompt_yes_no(prompt: str, *, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    while True:
        answer = input(prompt + suffix).strip().casefold()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please enter y or n.")


def _prompt_pin() -> str:
    while True:
        pin = getpass.getpass("Choose a shared household PIN or passphrase: ")
        try:
            validate_pin(pin)
        except ValueError as exc:
            print(f"{exc}.")
            continue
        confirmation = getpass.getpass("Enter it again: ")
        if pin == confirmation:
            return pin
        print("The entries did not match. Please try again.")


def _legacy_paths(legacy_root: Path) -> tuple[Path, Path, Path]:
    root = legacy_root.expanduser().resolve()
    source_dir = root / "receipts"
    receipts_csv = root / "parsed" / "receipts.csv"
    items_csv = root / "parsed" / "items.csv"
    missing = [
        path
        for path in (source_dir, receipts_csv, items_csv)
        if not path.exists()
    ]
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise CommandError(
            "The legacy archive is incomplete. These paths are missing:\n"
            f"{formatted}\n"
            "Pass --legacy-root with the source project directory, or use "
            "--skip-import."
        )
    return source_dir, receipts_csv, items_csv


def _configure_login(database, settings: Settings) -> tuple[bool, bool]:
    """Persist the signing secret and configure or deliberately retain the PIN."""

    with database.session() as session:
        get_or_create_session_secret(session, settings.session_secret)
        household = session.get(Household, 1)
        created = household is None
        rotate = created
        if not created:
            rotate = _prompt_yes_no(
                "A household PIN is already configured. Replace it?",
                default=False,
            )
            household.timezone = settings.timezone
            household.currency = settings.currency
        if rotate:
            display_name = DEFAULT_HOUSEHOLD_NAME
            if created:
                entered_name = input(
                    f"Household name [{DEFAULT_HOUSEHOLD_NAME}]: "
                ).strip()
                display_name = entered_name or DEFAULT_HOUSEHOLD_NAME
            else:
                display_name = household.display_name
            configure_household(
                session,
                _prompt_pin(),
                display_name=display_name,
                timezone=settings.timezone,
                currency=settings.currency,
            )
        return created, rotate


def _import_legacy(
    database,
    settings: Settings,
    *,
    legacy_root: Path,
    verify_expected_counts: bool,
) -> ImportSummary:
    source_dir, receipts_csv, items_csv = _legacy_paths(legacy_root)
    with database.session() as session:
        return import_existing(
            session,
            source_dir=source_dir,
            receipts_csv=receipts_csv,
            items_csv=items_csv,
            storage_dir=settings.receipt_dir,
            verify_expected_counts=verify_expected_counts,
        )


def _print_import_summary(summary: ImportSummary) -> None:
    state = "already present" if summary.already_imported else "imported"
    print(f"Legacy history {state}:")
    print(f"  Upload records:       {summary.uploads}")
    print(f"  Canonical receipts:   {summary.canonical_receipts}")
    print(f"  Duplicate receipts:   {summary.duplicate_receipts}")
    print(f"  Receipt items:        {summary.items}")
    print(f"  Managed files copied: {summary.files_copied}")


def setup_command(args: argparse.Namespace) -> int:
    """Run the idempotent, interactive first-time setup."""

    settings = _settings_for(args.data_dir)
    settings.ensure_directories()
    database = create_database(settings)
    try:
        schema = initialize_schema(database)
        print(f"Grocery Home data: {settings.data_dir}")
        print(f"Database schema:   {schema}")

        created, rotated = _configure_login(database, settings)
        if created:
            print("Household login created.")
        elif rotated:
            print("Household PIN replaced; earlier browser sessions are signed out.")
        else:
            print("Existing household PIN retained.")

        if args.skip_import:
            print("Legacy receipt import skipped.")
        else:
            summary = _import_legacy(
                database,
                settings,
                legacy_root=args.legacy_root,
                verify_expected_counts=not args.allow_unexpected_counts,
            )
            _print_import_summary(summary)

        with database.session() as session:
            refresh_analytics_snapshot(session)
        print("Initial analytics snapshot is ready.")
        print("Setup complete. Run .\\start_grocery_home.ps1 to start Grocery Home.")
        return 0
    finally:
        database.dispose()


def serve_command(args: argparse.Namespace) -> int:
    """Run the app on the LAN with exactly one Uvicorn worker."""

    settings = _settings_for(args.data_dir)
    settings.ensure_directories()
    database = create_database(settings)
    try:
        initialize_schema(database)
        with database.session() as session:
            configured = session.scalar(select(Household.id).limit(1)) is not None
        if not configured:
            raise CommandError(
                "No household login is configured. Run "
                ".\\start_grocery_home.ps1 -Setup first."
            )
    finally:
        database.dispose()

    # The web module resolves Settings from the environment. Propagate an
    # explicit CLI override before Uvicorn imports grocery_home.app.
    if args.data_dir is not None:
        os.environ["GROCERY_HOME_DATA_DIR"] = str(settings.data_dir)
        os.environ["GROCERY_HOME_DATABASE_URL"] = settings.database_url

    print(f"Grocery Home data: {settings.data_dir}")
    print(f"On this PC:        http://127.0.0.1:{args.port}")
    if args.host == DEFAULT_HOST:
        print(
            "On family devices: http://<this-PC-private-IP>:"
            f"{args.port} (see the README for the firewall step)"
        )

    import uvicorn

    uvicorn.run(
        "grocery_home.app:app",
        host=args.host,
        port=args.port,
        workers=1,
        proxy_headers=False,
        server_header=False,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (CommandError, ConfigurationError, LegacyImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled; no PIN was changed.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
