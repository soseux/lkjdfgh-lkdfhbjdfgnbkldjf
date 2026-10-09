from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text

from dota_predictor.config import Settings
from dota_predictor.db import build_engine, build_session_factory, session_scope
from dota_predictor.ingestion.opendota import OpenDotaClient
from dota_predictor.ingestion.raw_store import RawStore
from dota_predictor.ingestion.service import IngestionService
from dota_predictor.models import IngestionJob, Match
from dota_predictor.workers.match_worker import MatchWorker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dota-predictor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate", help="Apply all PostgreSQL migrations")
    subparsers.add_parser("status", help="Check the database and show ingestion counts")

    discover = subparsers.add_parser("discover", help="Discover professional matches")
    discover.add_argument("--pages", type=int, default=1)
    discover.add_argument("--less-than-match-id", type=int)

    fetch = subparsers.add_parser("fetch-match", help="Fetch one match immediately")
    fetch.add_argument("match_id", type=int)

    worker = subparsers.add_parser("worker", help="Process queued ingestion jobs")
    worker.add_argument("--once", action="store_true", help="Process at most one job")
    worker.add_argument(
        "--max-jobs",
        type=int,
        default=0,
        help="Stop after this many claims; zero means run forever",
    )
    return parser


def _client(settings: Settings) -> OpenDotaClient:
    return OpenDotaClient(
        settings.opendota_base_url,
        api_key=settings.opendota_api_key,
        requests_per_minute=settings.opendota_requests_per_minute,
        timeout_seconds=settings.http_timeout_seconds,
    )


def _service(settings: Settings, client: OpenDotaClient, session_factory) -> IngestionService:
    return IngestionService(
        client=client,
        raw_store=RawStore(settings.raw_data_dir),
        session_factory=session_factory,
    )


def _run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    if args.command == "migrate":
        alembic_config = Config("alembic.ini")
        alembic_config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
        command.upgrade(alembic_config, "head")
        return 0

    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    if args.command == "status":
        with session_scope(session_factory) as session:
            session.execute(text("SELECT 1"))
            matches = session.scalar(select(func.count()).select_from(Match))
            jobs = dict(
                session.execute(
                    select(IngestionJob.status, func.count()).group_by(IngestionJob.status)
                ).all()
            )
        print(json.dumps({"database": "ok", "matches": matches, "jobs": jobs}, indent=2))
        return 0

    with _client(settings) as client:
        service = _service(settings, client, session_factory)
        if args.command == "discover":
            result = service.discover_pro_matches(
                page_count=args.pages, less_than_match_id=args.less_than_match_id
            )
            print(json.dumps(asdict(result), indent=2))
            return 0
        if args.command == "fetch-match":
            match_id = service.fetch_and_normalize_match(args.match_id)
            print(json.dumps({"match_id": match_id, "status": "DETAILS_FETCHED"}, indent=2))
            return 0
        if args.command == "worker":
            worker = MatchWorker(
                worker_id=settings.worker_id,
                session_factory=session_factory,
                ingestion=service,
            )
            if args.once:
                processed = worker.process_one()
                print(json.dumps({"claimed": processed}))
                return 0
            if args.max_jobs > 0:
                processed = 0
                while processed < args.max_jobs and worker.process_one():
                    processed += 1
                print(json.dumps({"claimed": processed}))
                return 0
            worker.run_forever(poll_seconds=settings.worker_poll_seconds)
            return 0

    raise AssertionError(f"Unhandled command: {args.command}")


def main() -> None:
    try:
        raise SystemExit(_run(_parser().parse_args()))
    except KeyboardInterrupt:
        print("Stopped", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
