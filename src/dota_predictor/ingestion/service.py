from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from dota_predictor.db import session_scope
from dota_predictor.ingestion.opendota import OpenDotaClient
from dota_predictor.ingestion.raw_store import RawStore
from dota_predictor.repository import (
    normalize_match_detail,
    register_raw_object,
    upsert_pro_match_summaries,
)
from dota_predictor.workers.queue import JobQueue


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    pages: int
    matches_seen: int
    jobs_enqueued: int
    next_less_than_match_id: int | None


class IngestionService:
    def __init__(
        self,
        *,
        client: OpenDotaClient,
        raw_store: RawStore,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.client = client
        self.raw_store = raw_store
        self.session_factory = session_factory

    def discover_pro_matches(
        self, *, page_count: int, less_than_match_id: int | None = None
    ) -> DiscoveryResult:
        pages = 0
        matches_seen = 0
        jobs_enqueued = 0
        next_cursor = less_than_match_id

        for cursor, response in self.client.iter_pro_match_pages(
            page_count=page_count, less_than_match_id=less_than_match_id
        ):
            natural_key = f"before={cursor}" if cursor is not None else "latest"
            stored = self.raw_store.write_json(
                source="opendota",
                object_type="pro_matches",
                natural_key=natural_key,
                data=response.data,
            )
            with session_scope(self.session_factory) as session:
                register_raw_object(
                    session,
                    source="opendota",
                    object_type="pro_matches",
                    natural_key=natural_key,
                    response=response,
                    stored=stored,
                )
                match_ids = upsert_pro_match_summaries(session, response.data)
                for match_id in match_ids:
                    if JobQueue.enqueue(
                        session,
                        job_type="fetch_match_details",
                        match_id=match_id,
                        dedupe_key=f"fetch_match_details:{match_id}",
                        priority=10,
                    ):
                        jobs_enqueued += 1

            pages += 1
            matches_seen += len(response.data)
            page_match_ids = [int(row["match_id"]) for row in response.data if row.get("match_id")]
            if page_match_ids:
                next_cursor = min(page_match_ids)

        return DiscoveryResult(
            pages=pages,
            matches_seen=matches_seen,
            jobs_enqueued=jobs_enqueued,
            next_less_than_match_id=next_cursor,
        )

    def fetch_and_normalize_match(self, match_id: int) -> int:
        response = self.client.get_match(match_id)
        stored = self.raw_store.write_json(
            source="opendota",
            object_type="matches",
            natural_key=str(match_id),
            data=response.data,
        )
        with session_scope(self.session_factory) as session:
            register_raw_object(
                session,
                source="opendota",
                object_type="matches",
                natural_key=str(match_id),
                response=response,
                stored=stored,
            )
            return normalize_match_detail(session, response.data)
