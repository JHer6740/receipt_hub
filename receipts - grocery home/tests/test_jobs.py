from __future__ import annotations

from datetime import UTC, datetime, timedelta

from grocery_home.database import create_database, initialize_schema
from grocery_home.jobs import (
    SingleWorker,
    claim_next_job,
    complete_job,
    enqueue_job,
    fail_job,
    recover_stale_jobs,
)
from grocery_home.models import BackgroundJob, JobStatus


def memory_database():
    database = create_database(database_url="sqlite+pysqlite:///:memory:")
    initialize_schema(database)
    return database


def test_enqueue_dedupe_claim_and_complete() -> None:
    database = memory_database()
    with database.session() as session:
        first = enqueue_job(
            session,
            "receipt_extract",
            {"batch_id": "batch-1"},
            dedupe_key="receipt:batch-1",
        )
        second = enqueue_job(
            session,
            "receipt_extract",
            {"batch_id": "ignored"},
            dedupe_key="receipt:batch-1",
        )
        assert second.id == first.id

    with database.session() as session:
        claim = claim_next_job(session, "worker-a")
        assert claim is not None
        assert claim.payload == {"batch_id": "batch-1"}
        assert claim.attempts == 1

    with database.session() as session:
        completed = complete_job(session, claim.id, worker_id="worker-a")
        assert completed.status == JobStatus.COMPLETE
        assert completed.locked_by is None
        assert completed.finished_at is not None
    database.dispose()


def test_failure_retries_then_exhausts() -> None:
    database = memory_database()
    now = datetime(2026, 7, 24, 10, tzinfo=UTC)
    with database.session() as session:
        job = enqueue_job(
            session,
            "analysis",
            max_attempts=2,
            scheduled_for=now,
        )

    with database.session() as session:
        first = claim_next_job(session, "worker", now=now)
        assert first is not None
    with database.session() as session:
        failed = fail_job(
            session,
            first.id,
            "temporary",
            worker_id="worker",
            now=now,
            retry_delay=timedelta(0),
        )
        assert failed.status == JobStatus.QUEUED

    with database.session() as session:
        second = claim_next_job(session, "worker", now=now)
        assert second is not None
        assert second.attempts == 2
    with database.session() as session:
        failed = fail_job(
            session,
            second.id,
            "still broken",
            worker_id="worker",
            now=now,
        )
        assert failed.status == JobStatus.FAILED
        assert failed.last_error == "still broken"
    database.dispose()


def test_recovery_requeues_or_fails_stale_claims() -> None:
    database = memory_database()
    now = datetime(2026, 7, 24, 10, tzinfo=UTC)
    with database.session() as session:
        retry = enqueue_job(session, "retry", max_attempts=2, scheduled_for=now)
        exhaust = enqueue_job(session, "exhaust", max_attempts=1, scheduled_for=now)
    with database.session() as session:
        assert claim_next_job(session, "dead-a", now=now) is not None
        assert claim_next_job(session, "dead-b", now=now) is not None

    with database.session() as session:
        summary = recover_stale_jobs(
            session,
            now=now + timedelta(hours=1),
            lock_timeout=timedelta(minutes=5),
        )
        assert summary.requeued == 1
        assert summary.failed == 1
        assert session.get(BackgroundJob, retry.id).status == JobStatus.QUEUED
        assert session.get(BackgroundJob, exhaust.id).status == JobStatus.FAILED
    database.dispose()


def test_single_worker_rolls_back_handler_before_recording_retry() -> None:
    database = memory_database()
    with database.session() as session:
        job = enqueue_job(session, "explode", max_attempts=1)

    def explode(_session, _payload):
        raise RuntimeError("handler failed")

    worker = SingleWorker(database, {"explode": explode}, worker_id="test-worker")
    assert worker.run_once().id == job.id

    with database.session() as session:
        stored = session.get(BackgroundJob, job.id)
        assert stored.status == JobStatus.FAILED
        assert stored.last_error == "handler failed"
    database.dispose()
