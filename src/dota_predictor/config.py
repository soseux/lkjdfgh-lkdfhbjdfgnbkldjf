from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    value = default if raw is None else float(raw)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    opendota_base_url: str
    opendota_api_key: str | None
    opendota_requests_per_minute: float
    http_timeout_seconds: float
    raw_data_dir: Path
    worker_id: str
    worker_poll_seconds: float

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv()
        return cls(
            database_url=os.getenv(
                "DOTA_DATABASE_URL",
                "postgresql+psycopg://dota:dota@localhost:5432/dota_predictor",
            ),
            opendota_base_url=os.getenv(
                "DOTA_OPENDOTA_BASE_URL", "https://api.opendota.com/api"
            ).rstrip("/"),
            opendota_api_key=os.getenv("DOTA_OPENDOTA_API_KEY") or None,
            opendota_requests_per_minute=_positive_float("DOTA_OPENDOTA_REQUESTS_PER_MINUTE", 50),
            http_timeout_seconds=_positive_float("DOTA_HTTP_TIMEOUT_SECONDS", 30),
            raw_data_dir=Path(os.getenv("DOTA_RAW_DATA_DIR", "data/raw")),
            worker_id=os.getenv("DOTA_WORKER_ID", "local-worker"),
            worker_poll_seconds=_positive_float("DOTA_WORKER_POLL_SECONDS", 2),
        )
