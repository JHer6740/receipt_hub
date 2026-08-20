"""Durable SQLite-backed background jobs for the single-process LAN app."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from grocery_home.database import Database
from grocery_home.models import BackgroundJob, JobStatus, new_id


DEFAULT_LOCK_TIMEOUT = timedelta(minutes=15)
MAX_ERROR_LENGTH = 4000


class JobStateError(RuntimeError):
    """A job transition was requested from an incompatible durable state."""


@dataclass(frozen=True, slots=True)
class JobClaim:
    id: str
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    worker_id: str


@dataclass(frozen=True, slots=True)
class RecoverySummary:
    requeued: int
    failed: int


JobHandler = Callable[[Session, Mapping[str, Any]], None]


def enqueue_job(
    session: Session,
    kind: str,
    payload: Mapping[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
    max_attempts: int = 3,
    scheduled_for: datetime | None = None,
) -> BackgroundJob:
    """Add a durable job, returning the existing row for a duplicate key."""

    clean_kind = kind.strip()
    if not clean_kind:
        raise ValueError("A background job kind is required.")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one.")
    if dedupe_key is not None:
        dedupe_key = dedupe_key.strip() or None
    if dedupe_key:
        existing = session.scalar(
            select(BackgroundJob).where(BackgroundJob.dedupe_key == dedupe_key)
        )
        if existing is not None:
            return existing

    job = BackgroundJob(
        id=new_id(),
        kind=clean_kind,
        status=JobStatus.QUEUED,
        payload=dict(payload or {}),
        dedupe_key=dedupe_key,
        max_attempts=max_attempts,
        scheduled_for=_utc(scheduled_for or _now()),
    )
    if not dedupe_key:
        session.add(job)
        session.flush()
        return job

    # The savepoint handles two callers racing on the same unique dedupe key
    # without poisoning the caller's outer transaction.
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
        return job
    except IntegrityError:
        existing = session.scalar(
            select(BackgroundJob).where(BackgroundJob.dedupe_key == dedupe_key)
        )
        if existing is None:  # defensive: a non-dedupe constraint failed
            raise
        return existing


def claim_next_job(
    session: Session,
    worker_id: str,
    *,
    now: datetime | None = None,
) -> JobClaim | None:
    """Atomically claim the oldest runnable job.

    Claiming only holds a database transaction for one UPDATE.  The caller
    should commit its session before running the handler so other LAN requests
    are never blocked by long analytics or OCR work.
    """

    worker_id = worker_id.strip()
    if not worker_id:
        raise ValueError("worker_id is required.")
    claimed_at = _utc(now or _now())
    candidates: Select[tuple[str]] = (
        select(BackgroundJob.id)
        .where(
            BackgroundJob.status == JobStatus.QUEUED,
            BackgroundJob.scheduled_for <= claimed_at,
            BackgroundJob.attempts < BackgroundJob.max_attempts,
        )
        .order_by(BackgroundJob.scheduled_for, BackgroundJob.created_at)
        .limit(8)
    )
    for job_id in session.scalars(candidates):
        result = session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.id == job_id,
                BackgroundJob.status == JobStatus.QUEUED,
                BackgroundJob.attempts < BackgroundJob.max_attempts,
            )
            .values(
                status=JobStatus.RUNNING,
                attempts=BackgroundJob.attempts + 1,
                locked_at=claimed_at,
                locked_by=worker_id,
                started_at=claimed_at,
                finished_at=None,
            )
        )
        if result.rowcount != 1:
            continue
        session.flush()
        session.expire_all()
        job = session.get(BackgroundJob, job_id)
        if job is None:
            continue
        return JobClaim(
            id=job.id,
            kind=job.kind,
            payload=dict(job.payload or {}),
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            worker_id=worker_id,
        )
    return None


def recover_stale_jobs(
    session: Session,
    *,
    now: datetime | None = None,
    lock_timeout: timedelta = DEFAULT_LOCK_TIMEOUT,
) -> RecoverySummary:
    """Requeue interrupted jobs, permanently failing exhausted attempts."""

    if lock_timeout.total_seconds() <= 0:
        raise ValueError("lock_timeout must be positive.")
    current = _utc(now or _now())
    stale_before = current - lock_timeout
    jobs = list(
        session.scalars(
            select(BackgroundJob).where(
                BackgroundJob.status == JobStatus.RUNNING,
                BackgroundJob.locked_at.is_not(None),
                BackgroundJob.locked_at < stale_before,
            )
        )
    )
    requeued = failed = 0
    for job in jobs:
        job.locked_at = None
        job.locked_by = None
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.FAILED
            job.finished_at = current
            job.last_error = _error_text(
                job.last_error or "Worker stopped before completing the job."
            )
            failed += 1
        else:
            job.status = JobStatus.QUEUED
            job.started_at = None
            job.finished_at = None
            job.scheduled_for = current
            job.last_error = _error_text(
                job.last_error or "Recovered after an interrupted worker."
            )
            requeued += 1
    session.flush()
    return RecoverySummary(requeued=requeued, failed=failed)


def heartbeat_job(
    session: Session,
    job_id: str,
    worker_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    result = session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.status == JobStatus.RUNNING,
            BackgroundJob.locked_by == worker_id,
        )
        .values(locked_at=_utc(now or _now()))
    )
    session.flush()
    return result.rowcount == 1


def complete_job(
    session: Session,
    job_id: str,
    *,
    worker_id: str | None = None,
    now: datetime | None = None,
) -> BackgroundJob:
    job = _running_job(session, job_id, worker_id)
    job.status = JobStatus.COMPLETE
    job.finished_at = _utc(now or _now())
    job.locked_at = None
    job.locked_by = None
    job.last_error = None
    session.flush()
    return job


def fail_job(
    session: Session,
    job_id: str,
    error: BaseException | str,
    *,
    worker_id: str | None = None,
    retryable: bool = True,
    now: datetime | None = None,
    retry_delay: timedelta | None = None,
) -> BackgroundJob:
    """Record failure, requeueing until ``max_attempts`` is exhausted."""

    job = _running_job(session, job_id, worker_id)
    current = _utc(now or _now())
    job.last_error = _error_text(error)
    job.locked_at = None
    job.locked_by = None
    if retryable and job.attempts < job.max_attempts:
        job.status = JobStatus.QUEUED
        job.started_at = None
        job.finished_at = None
        delay = (
            retry_delay
            if retry_delay is not None
            else timedelta(seconds=min(300, 5 * (2 ** (job.attempts - 1))))
        )
        job.scheduled_for = current + delay
    else:
        job.status = JobStatus.FAILED
        job.finished_at = current
    session.flush()
    return job


class SingleWorker:
    """Run registered handlers one at a time with durable state transitions."""

    def __init__(
        self,
        database: Database,
        handlers: Mapping[str, JobHandler],
        *,
        worker_id: str | None = None,
    ) -> None:
        self.database = database
        self.handlers = dict(handlers)
        self.worker_id = worker_id or f"grocery-home-{new_id()[:12]}"

    def recover(self, *, lock_timeout: timedelta = DEFAULT_LOCK_TIMEOUT) -> RecoverySummary:
        with self.database.session() as session:
            return recover_stale_jobs(session, lock_timeout=lock_timeout)

    def run_once(self) -> JobClaim | None:
        with self.database.session() as session:
            claim = claim_next_job(session, self.worker_id)
        if claim is None:
            return None

        handler = self.handlers.get(claim.kind)
        if handler is None:
            with self.database.session() as session:
                fail_job(
                    session,
                    claim.id,
                    f"No handler is registered for job kind {claim.kind!r}.",
                    worker_id=self.worker_id,
                    retryable=False,
                )
            return claim

        try:
            with self.database.session() as session:
                handler(session, claim.payload)
                complete_job(session, claim.id, worker_id=self.worker_id)
        except Exception as exc:
            with self.database.session() as session:
                fail_job(
                    session,
                    claim.id,
                    exc,
                    worker_id=self.worker_id,
                    retryable=True,
                )
        return claim

    def run_available(self, *, limit: int = 100) -> int:
        if limit < 1:
            raise ValueError("limit must be at least one.")
        processed = 0
        while processed < limit and self.run_once() is not None:
            processed += 1
        return processed


def _running_job(
    session: Session, job_id: str, worker_id: str | None
) -> BackgroundJob:
    job = session.get(BackgroundJob, job_id)
    if job is None:
        raise JobStateError(f"Background job {job_id} does not exist.")
    if job.status != JobStatus.RUNNING:
        raise JobStateError(
            f"Background job {job_id} is {job.status.value}, not running."
        )
    if worker_id is not None and job.locked_by != worker_id:
        raise JobStateError(f"Background job {job_id} is owned by another worker.")
    return job


def _error_text(error: BaseException | str) -> str:
    text = str(error).strip() or error.__class__.__name__
    return text[:MAX_ERROR_LENGTH]


def _now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "DEFAULT_LOCK_TIMEOUT",
    "JobClaim",
    "JobHandler",
    "JobStateError",
    "RecoverySummary",
    "SingleWorker",
    "claim_next_job",
    "complete_job",
    "enqueue_job",
    "fail_job",
    "heartbeat_job",
    "recover_stale_jobs",
]
