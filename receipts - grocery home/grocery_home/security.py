"""Shared-PIN authentication, signed sessions, CSRF and login throttling."""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import and_, case, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response

from .models import AppSetting, Household, PinAttempt


SESSION_SALT = "grocery-home.session.v1"
SESSION_PAYLOAD_VERSION = 1
MINIMUM_PIN_LENGTH = 4
MAXIMUM_PIN_LENGTH = 64
SESSION_SECRET_SETTING = "security.session_secret"

_PIN_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


class InvalidSessionError(ValueError):
    """Raised when a session cookie is missing, expired or malformed."""


def validate_pin(pin: str) -> str:
    """Validate a PIN without forcing it to be numeric.

    Families may choose a short passphrase; limiting encoded length avoids
    unexpectedly expensive hashing of attacker-controlled payloads.
    """

    if not isinstance(pin, str):
        raise TypeError("PIN must be a string")
    if not MINIMUM_PIN_LENGTH <= len(pin) <= MAXIMUM_PIN_LENGTH:
        raise ValueError(
            f"PIN must be {MINIMUM_PIN_LENGTH} to {MAXIMUM_PIN_LENGTH} characters"
        )
    return pin


def hash_pin(pin: str) -> str:
    return _PIN_HASHER.hash(validate_pin(pin))


def verify_pin(pin_hash: str, candidate: str) -> bool:
    try:
        validate_pin(candidate)
        return _PIN_HASHER.verify(pin_hash, candidate)
    except (
        InvalidHashError,
        VerificationError,
        VerifyMismatchError,
        TypeError,
        ValueError,
    ):
        return False


def pin_hash_needs_rehash(pin_hash: str) -> bool:
    try:
        return _PIN_HASHER.check_needs_rehash(pin_hash)
    except (InvalidHashError, VerificationError):
        return True


def generate_session_secret() -> str:
    """Generate enough entropy for the persisted application session secret."""

    return secrets.token_urlsafe(48)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf_token(expected: str, supplied: str | None) -> bool:
    if not supplied or not expected:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))


def get_or_create_session_secret(
    session: Session,
    configured_secret: str | None = None,
) -> str:
    """Resolve an environment override or persist a generated local secret."""

    if configured_secret is not None:
        if len(configured_secret) < 32:
            raise ValueError("Configured session secret must contain at least 32 characters")
        return configured_secret

    setting = session.get(AppSetting, SESSION_SECRET_SETTING)
    if setting is None:
        secret = generate_session_secret()
        session.add(AppSetting(key=SESSION_SECRET_SETTING, value=secret))
        session.flush()
        return secret
    if len(setting.value) < 32:
        raise ValueError("Persisted session secret is invalid")
    return setting.value


def configure_household(
    session: Session,
    pin: str,
    *,
    display_name: str = "Our household",
    timezone: str = "Australia/Sydney",
    currency: str = "AUD",
) -> Household:
    """Create the singleton household or rotate its shared PIN and sessions."""

    household = session.get(Household, 1)
    if household is None:
        household = Household(
            id=1,
            display_name=display_name.strip() or "Our household",
            pin_hash=hash_pin(pin),
            timezone=timezone,
            currency=currency.upper(),
        )
        session.add(household)
    else:
        household.display_name = display_name.strip() or household.display_name
        household.pin_hash = hash_pin(pin)
        household.timezone = timezone
        household.currency = currency.upper()
        household.session_generation += 1
    session.flush()
    return household


@dataclass(frozen=True, slots=True)
class SessionData:
    household_id: int
    generation: int
    csrf_token: str


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    data: SessionData


class SessionManager:
    """Create and verify signed, time-limited household sessions."""

    def __init__(
        self,
        secret: str,
        *,
        cookie_name: str = "grocery_home_session",
        max_age_seconds: int = 60 * 60 * 24 * 30,
        secure_cookie: bool = False,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("Session secret must contain at least 32 characters")
        if max_age_seconds <= 0:
            raise ValueError("Session max age must be greater than zero")
        self.cookie_name = cookie_name
        self.max_age_seconds = max_age_seconds
        self.secure_cookie = secure_cookie
        self._serializer = URLSafeTimedSerializer(
            secret_key=secret,
            salt=SESSION_SALT,
            signer_kwargs={"digest_method": hashlib.sha256},
        )

    def issue(self, household_id: int, generation: int) -> IssuedSession:
        data = SessionData(
            household_id=household_id,
            generation=generation,
            csrf_token=generate_csrf_token(),
        )
        payload = {
            "v": SESSION_PAYLOAD_VERSION,
            "sub": data.household_id,
            "gen": data.generation,
            "csrf": data.csrf_token,
        }
        return IssuedSession(token=self._serializer.dumps(payload), data=data)

    def load(self, token: str | None) -> SessionData:
        if not token:
            raise InvalidSessionError("Session cookie is missing")
        try:
            payload = self._serializer.loads(
                token,
                max_age=self.max_age_seconds,
            )
        except SignatureExpired as exc:
            raise InvalidSessionError("Session has expired") from exc
        except BadSignature as exc:
            raise InvalidSessionError("Session signature is invalid") from exc

        try:
            version = int(payload["v"])
            household_id = int(payload["sub"])
            generation = int(payload["gen"])
            csrf_token = str(payload["csrf"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidSessionError("Session payload is invalid") from exc

        if version != SESSION_PAYLOAD_VERSION or len(csrf_token) < 32:
            raise InvalidSessionError("Session payload is invalid")

        return SessionData(
            household_id=household_id,
            generation=generation,
            csrf_token=csrf_token,
        )

    def load_request(self, request: Request) -> SessionData:
        return self.load(request.cookies.get(self.cookie_name))

    def set_cookie(self, response: Response, issued: IssuedSession) -> None:
        response.set_cookie(
            key=self.cookie_name,
            value=issued.token,
            max_age=self.max_age_seconds,
            httponly=True,
            secure=self.secure_cookie,
            samesite="lax",
            path="/",
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(
            key=self.cookie_name,
            httponly=True,
            secure=self.secure_cookie,
            samesite="lax",
            path="/",
        )


@dataclass(frozen=True, slots=True)
class ThrottleDecision:
    allowed: bool
    retry_after_seconds: int = 0
    failure_count: int = 0


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    authenticated: bool
    rate_limited: bool = False
    retry_after_seconds: int = 0


class PinThrottle:
    """Database-backed fixed-window PIN throttle.

    The process lock prevents lost increments within the supported
    single-process Uvicorn deployment, while the database rows retain lockout
    state across restarts.
    """

    _process_lock = threading.RLock()

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: int = 15 * 60,
        lock_seconds: int = 15 * 60,
        fingerprint_pepper: str = "",
    ) -> None:
        if min(max_failures, window_seconds, lock_seconds) <= 0:
            raise ValueError("Throttle limits must all be greater than zero")
        self.max_failures = max_failures
        self.window = timedelta(seconds=window_seconds)
        self.lock_duration = timedelta(seconds=lock_seconds)
        self.fingerprint_pepper = fingerprint_pepper.encode("utf-8")

    def fingerprint(self, attempt_key: str) -> str:
        normalized = attempt_key.strip() or "unknown"
        if self.fingerprint_pepper:
            return hmac.new(
                self.fingerprint_pepper,
                normalized.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def check(
        self,
        session: Session,
        attempt_key: str,
        *,
        now: datetime | None = None,
    ) -> ThrottleDecision:
        checked_at = _as_utc(now or datetime.now(UTC))
        row = session.get(PinAttempt, self.fingerprint(attempt_key))
        if row is None:
            return ThrottleDecision(allowed=True)

        if row.locked_until is not None and _as_utc(row.locked_until) > checked_at:
            return ThrottleDecision(
                allowed=False,
                retry_after_seconds=_seconds_until(row.locked_until, checked_at),
                failure_count=row.failure_count,
            )
        return ThrottleDecision(
            allowed=True,
            failure_count=row.failure_count,
        )

    def record_failure(
        self,
        session: Session,
        attempt_key: str,
        *,
        now: datetime | None = None,
    ) -> ThrottleDecision:
        failed_at = _as_utc(now or datetime.now(UTC))
        key_hash = self.fingerprint(attempt_key)

        with self._process_lock:
            if session.get_bind().dialect.name == "sqlite":
                return self._record_failure_sqlite(session, key_hash, failed_at)

            row = session.get(PinAttempt, key_hash)
            if row is None:
                row = PinAttempt(
                    attempt_key_hash=key_hash,
                    failure_count=1,
                    window_started_at=failed_at,
                    last_attempt_at=failed_at,
                )
                session.add(row)
            elif row.locked_until is not None and _as_utc(row.locked_until) > failed_at:
                row.last_attempt_at = failed_at
                session.flush()
                return ThrottleDecision(
                    allowed=False,
                    retry_after_seconds=_seconds_until(row.locked_until, failed_at),
                    failure_count=row.failure_count,
                )
            elif (
                row.locked_until is not None
                or failed_at - _as_utc(row.window_started_at) >= self.window
            ):
                row.failure_count = 1
                row.window_started_at = failed_at
                row.locked_until = None
                row.last_attempt_at = failed_at
            else:
                row.failure_count += 1
                row.last_attempt_at = failed_at

            if row.failure_count >= self.max_failures:
                row.locked_until = failed_at + self.lock_duration

            session.flush()
            if row.locked_until is not None and _as_utc(row.locked_until) > failed_at:
                return ThrottleDecision(
                    allowed=False,
                    retry_after_seconds=_seconds_until(row.locked_until, failed_at),
                    failure_count=row.failure_count,
                )
            return ThrottleDecision(
                allowed=True,
                failure_count=row.failure_count,
            )

    def _record_failure_sqlite(
        self,
        session: Session,
        key_hash: str,
        failed_at: datetime,
    ) -> ThrottleDecision:
        """Atomically increment the throttle row across concurrent requests."""

        window_cutoff = failed_at - self.window
        lock_until = failed_at + self.lock_duration
        active_lock = and_(
            PinAttempt.locked_until.is_not(None),
            PinAttempt.locked_until > failed_at,
        )
        reset_window = or_(
            and_(
                PinAttempt.locked_until.is_not(None),
                PinAttempt.locked_until <= failed_at,
            ),
            PinAttempt.window_started_at <= window_cutoff,
        )
        incremented_count = PinAttempt.failure_count + 1
        updated_count = case(
            (active_lock, PinAttempt.failure_count),
            (reset_window, 1),
            else_=incremented_count,
        )
        reset_lock = lock_until if self.max_failures == 1 else None
        updated_lock = case(
            (active_lock, PinAttempt.locked_until),
            (reset_window, reset_lock),
            (incremented_count >= self.max_failures, lock_until),
            else_=None,
        )
        inserted_lock = lock_until if self.max_failures == 1 else None

        statement = sqlite_insert(PinAttempt).values(
            attempt_key_hash=key_hash,
            failure_count=1,
            window_started_at=failed_at,
            last_attempt_at=failed_at,
            locked_until=inserted_lock,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[PinAttempt.attempt_key_hash],
            set_={
                "failure_count": updated_count,
                "window_started_at": case(
                    (reset_window, failed_at),
                    else_=PinAttempt.window_started_at,
                ),
                "last_attempt_at": failed_at,
                "locked_until": updated_lock,
            },
        )
        session.execute(statement)
        session.flush()
        row = session.scalar(
            select(PinAttempt)
            .where(PinAttempt.attempt_key_hash == key_hash)
            .execution_options(populate_existing=True)
        )
        if row is None:  # pragma: no cover - defensive against driver corruption
            raise RuntimeError("PIN throttle row was not persisted")
        if row.locked_until is not None and _as_utc(row.locked_until) > failed_at:
            return ThrottleDecision(
                allowed=False,
                retry_after_seconds=_seconds_until(row.locked_until, failed_at),
                failure_count=row.failure_count,
            )
        return ThrottleDecision(
            allowed=True,
            failure_count=row.failure_count,
        )

    def record_success(self, session: Session, attempt_key: str) -> None:
        with self._process_lock:
            row = session.get(PinAttempt, self.fingerprint(attempt_key))
            if row is not None:
                session.delete(row)
                session.flush()


def authenticate_shared_pin(
    session: Session,
    household: Household,
    candidate_pin: str,
    attempt_key: str,
    throttle: PinThrottle,
    *,
    now: datetime | None = None,
) -> AuthenticationResult:
    """Authenticate and update persistent throttle state in one transaction."""

    decision = throttle.check(session, attempt_key, now=now)
    if not decision.allowed:
        return AuthenticationResult(
            authenticated=False,
            rate_limited=True,
            retry_after_seconds=decision.retry_after_seconds,
        )

    if not verify_pin(household.pin_hash, candidate_pin):
        failure = throttle.record_failure(session, attempt_key, now=now)
        return AuthenticationResult(
            authenticated=False,
            rate_limited=not failure.allowed,
            retry_after_seconds=failure.retry_after_seconds,
        )

    throttle.record_success(session, attempt_key)
    if pin_hash_needs_rehash(household.pin_hash):
        household.pin_hash = hash_pin(candidate_pin)
        session.flush()
    return AuthenticationResult(authenticated=True)


def session_matches_household(data: SessionData, household: Household) -> bool:
    """Reject sessions issued before a PIN/session-generation rotation."""

    return (
        data.household_id == household.id
        and data.generation == household.session_generation
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _seconds_until(future: datetime, now: datetime) -> int:
    remaining = (_as_utc(future) - _as_utc(now)).total_seconds()
    return max(0, math.ceil(remaining))


__all__ = [
    "AuthenticationResult",
    "InvalidSessionError",
    "IssuedSession",
    "PinThrottle",
    "SessionData",
    "SessionManager",
    "ThrottleDecision",
    "authenticate_shared_pin",
    "generate_csrf_token",
    "generate_session_secret",
    "get_or_create_session_secret",
    "hash_pin",
    "pin_hash_needs_rehash",
    "session_matches_household",
    "configure_household",
    "validate_pin",
    "verify_csrf_token",
    "verify_pin",
]
