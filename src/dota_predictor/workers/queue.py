from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from dota_predictor.models import IngestionJob


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job_id: int
    job_type: str
    match_id: int | None
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


def retry_delay_seconds(attempts: int) -> int:
    return min(3600, 5 * (2 ** min(max(attempts - 1, 0), 10)))


class JobQueue:
    @staticmethod
    def enqueue(
        session: Session,
        *,
        job_type: str,
        dedupe_key: str,
        match_id: int | None = None,
        payload: dict[str, Any] | None = None,
        priority: int = 0,
        max_attempts: int = 5,
    ) -> bool:
        statement = (
            insert(IngestionJob)
            .values(
                job_type=job_type,
                match_id=match_id,
                payload=payload or {},
                dedupe_key=dedupe_key,
                status="pending",
                priority=priority,
                attempts=0,
                max_attempts=max_attempts,
            )
            .on_conflict_do_nothing(index_elements=[IngestionJob.dedupe_key])
            .returning(IngestionJob.job_id)
        )
        return session.execute(statement).scalar_one_or_none() is not None

    @staticmethod
    def claim(session: Session, *, worker_id: str) -> ClaimedJob | None:
        row = (
            session.execute(
                text(
                    """
                    WITH candidate AS (
                        SELECT job_id
                        FROM ingestion_jobs
                        WHERE status IN ('pending', 'retry')
                          AND available_at <= now()
                        ORDER BY priority DESC, available_at ASC, job_id ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE ingestion_jobs AS job
                    SET status = 'running',
                        attempts = job.attempts + 1,
                        locked_at = now(),
                        worker_id = :worker_id,
                        last_error = NULL
                    FROM candidate
                    WHERE job.job_id = candidate.job_id
                    RETURNING job.job_id, job.job_type, job.match_id, job.payload,
                              job.attempts, job.max_attempts
                    """
                ),
                {"worker_id": worker_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return ClaimedJob(
            job_id=row["job_id"],
            job_type=row["job_type"],
            match_id=row["match_id"],
            payload=dict(row["payload"] or {}),
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
        )

    @staticmethod
    def complete(session: Session, *, job_id: int, worker_id: str) -> None:
        result = session.execute(
            update(IngestionJob)
            .where(
                IngestionJob.job_id == job_id,
                IngestionJob.status == "running",
                IngestionJob.worker_id == worker_id,
            )
            .values(
                status="succeeded",
                finished_at=datetime.now(UTC),
                locked_at=None,
                worker_id=None,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError(f"Job {job_id} is not owned by worker {worker_id}")

    @staticmethod
    def fail(session: Session, *, job_id: int, worker_id: str, error: str) -> str:
        job = session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.job_id == job_id,
                IngestionJob.status == "running",
                IngestionJob.worker_id == worker_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if job is None:
            raise RuntimeError(f"Job {job_id} is not owned by worker {worker_id}")

        now = datetime.now(UTC)
        job.last_error = error[-8000:]
        job.locked_at = None
        job.worker_id = None
        if job.attempts >= job.max_attempts:
            job.status = "dead"
            job.finished_at = now
        else:
            job.status = "retry"
            job.available_at = now + timedelta(seconds=retry_delay_seconds(job.attempts))
        return job.status

    @staticmethod
    def requeue_stale(session: Session, *, older_than_seconds: int = 900) -> int:
        result = session.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'retry',
                    available_at = now(),
                    locked_at = NULL,
                    worker_id = NULL,
                    last_error = 'Recovered stale worker lock'
                WHERE status = 'running'
                  AND locked_at < now() - make_interval(secs => :older_than_seconds)
                """
            ),
            {"older_than_seconds": older_than_seconds},
        )
        return result.rowcount
