"""Application configuration and runtime directory handling.

Configuration is intentionally small and environment driven.  Importing this
module does not create directories; callers opt in by calling
``Settings.ensure_directories`` during setup or application startup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping


class ConfigurationError(ValueError):
    """Raised when an environment setting cannot be parsed safely."""


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"Expected a boolean value, received {value!r}")


def _parse_positive_int(
    value: str | None,
    *,
    default: int,
    setting_name: str,
) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{setting_name} must be an integer") from exc
    if parsed <= 0:
        raise ConfigurationError(f"{setting_name} must be greater than zero")
    return parsed


def default_data_directory(env: Mapping[str, str] | None = None) -> Path:
    """Return the platform-appropriate Grocery Home application data path."""

    source = os.environ if env is None else env
    if configured := source.get("GROCERY_HOME_DATA_DIR"):
        return Path(configured).expanduser()

    if local_app_data := source.get("LOCALAPPDATA"):
        return Path(local_app_data) / "GroceryHome"

    if os.name == "nt":
        return Path.home() / "AppData" / "Local" / "GroceryHome"

    xdg_data_home = source.get("XDG_DATA_HOME")
    base = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
    return base / "GroceryHome"


def sqlite_url(database_path: Path) -> str:
    """Build a SQLAlchemy SQLite URL without Windows backslash ambiguity."""

    absolute = database_path.expanduser().absolute()
    return f"sqlite+pysqlite:///{absolute.as_posix()}"


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings shared by the web, worker and setup commands."""

    data_dir: Path
    database_url: str
    session_secret: str | None = None
    session_cookie_name: str = "grocery_home_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 30
    secure_cookies: bool = False
    max_upload_bytes: int = 20 * 1024 * 1024
    max_photo_files: int = 5
    max_pdf_pages: int = 10
    pin_max_failures: int = 5
    pin_window_seconds: int = 15 * 60
    pin_lock_seconds: int = 15 * 60
    timezone: str = "Australia/Sydney"
    currency: str = "AUD"

    @property
    def database_path(self) -> Path:
        """Return the default DB path, even if a custom DB URL is configured."""

        return self.data_dir / "grocery_home.sqlite3"

    @property
    def receipt_dir(self) -> Path:
        return self.data_dir / "receipts"

    @property
    def temporary_dir(self) -> Path:
        return self.data_dir / "tmp"

    def ensure_directories(self) -> None:
        """Create runtime directories with no dependency on the project tree."""

        for directory in (self.data_dir, self.receipt_dir, self.temporary_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        data_dir = default_data_directory(source)
        database_url = source.get("GROCERY_HOME_DATABASE_URL") or sqlite_url(
            data_dir / "grocery_home.sqlite3"
        )

        return cls(
            data_dir=data_dir,
            database_url=database_url,
            session_secret=source.get("GROCERY_HOME_SESSION_SECRET") or None,
            session_cookie_name=source.get(
                "GROCERY_HOME_SESSION_COOKIE", "grocery_home_session"
            ),
            session_max_age_seconds=_parse_positive_int(
                source.get("GROCERY_HOME_SESSION_MAX_AGE"),
                default=60 * 60 * 24 * 30,
                setting_name="GROCERY_HOME_SESSION_MAX_AGE",
            ),
            secure_cookies=_parse_bool(
                source.get("GROCERY_HOME_SECURE_COOKIES"), default=False
            ),
            max_upload_bytes=_parse_positive_int(
                source.get("GROCERY_HOME_MAX_UPLOAD_BYTES"),
                default=20 * 1024 * 1024,
                setting_name="GROCERY_HOME_MAX_UPLOAD_BYTES",
            ),
            max_photo_files=_parse_positive_int(
                source.get("GROCERY_HOME_MAX_PHOTO_FILES"),
                default=5,
                setting_name="GROCERY_HOME_MAX_PHOTO_FILES",
            ),
            max_pdf_pages=_parse_positive_int(
                source.get("GROCERY_HOME_MAX_PDF_PAGES"),
                default=10,
                setting_name="GROCERY_HOME_MAX_PDF_PAGES",
            ),
            pin_max_failures=_parse_positive_int(
                source.get("GROCERY_HOME_PIN_MAX_FAILURES"),
                default=5,
                setting_name="GROCERY_HOME_PIN_MAX_FAILURES",
            ),
            pin_window_seconds=_parse_positive_int(
                source.get("GROCERY_HOME_PIN_WINDOW_SECONDS"),
                default=15 * 60,
                setting_name="GROCERY_HOME_PIN_WINDOW_SECONDS",
            ),
            pin_lock_seconds=_parse_positive_int(
                source.get("GROCERY_HOME_PIN_LOCK_SECONDS"),
                default=15 * 60,
                setting_name="GROCERY_HOME_PIN_LOCK_SECONDS",
            ),
            timezone=source.get("GROCERY_HOME_TIMEZONE", "Australia/Sydney"),
            currency=source.get("GROCERY_HOME_CURRENCY", "AUD").upper(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process settings; clear the cache in tests after changing env."""

    return Settings.from_env()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


__all__ = [
    "ConfigurationError",
    "Settings",
    "clear_settings_cache",
    "default_data_directory",
    "get_settings",
    "sqlite_url",
]
