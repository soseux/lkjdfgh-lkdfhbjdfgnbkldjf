from __future__ import annotations

import time
import traceback

from sqlalchemy.orm import Session, sessionmaker

from dota_predictor.db import session_scope
from dota_predictor.ingestion.service import IngestionService
from dota_predictor.workers.queue import ClaimedJob, JobQueue


class MatchWorker:
    def __init__(
        self,
        *,
        worker_id: str,
        session_factory: sessionmaker[Session],
        ingestion: IngestionService,
    ) -> None:
        self.worker_id = worker_id
        self.session_factory = session_factory
        self.ingestion = ingestion

    def _handle(self, job: ClaimedJob) -> None:
        if job.job_type == "fetch_match_details":
            if job.match_id is None:
                raise ValueError("fetch_match_details job has no match_id")
            self.ingestion.fetch_and_normalize_match(job.match_id)
            return
        raise ValueError(f"Unsupported job type: {job.job_type}")

    def process_one(self) -> bool:
        with session_scope(self.session_factory) as session:
            job = JobQueue.claim(session, worker_id=self.worker_id)
        if job is None:
            return False

        try:
            self._handle(job)
        except Exception:
            error = traceback.format_exc()
            with session_scope(self.session_factory) as session:
                JobQueue.fail(
                    session,
                    job_id=job.job_id,
                    worker_id=self.worker_id,
                    error=error,
                )
            return True

        with session_scope(self.session_factory) as session:
            JobQueue.complete(session, job_id=job.job_id, worker_id=self.worker_id)
        return True

    def run_forever(self, *, poll_seconds: float) -> None:
        with session_scope(self.session_factory) as session:
            JobQueue.requeue_stale(session)
        while True:
            if not self.process_one():
                time.sleep(poll_seconds)
