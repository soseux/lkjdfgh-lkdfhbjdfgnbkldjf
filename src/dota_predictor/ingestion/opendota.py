from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import httpx


@dataclass(frozen=True, slots=True)
class ApiResponse[JsonT: (list[dict[str, Any]], dict[str, Any])]:
    data: JsonT
    url: str
    status_code: int
    headers: dict[str, str]
    fetched_at: datetime

    @property
    def source_version(self) -> str | None:
        return self.headers.get("etag") or self.headers.get("last-modified")


class OpenDotaClient:
    """Small rate-limited client for the two endpoints used by the first pipeline."""

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    RETAINED_HEADERS = {
        "etag",
        "last-modified",
        "x-rate-limit-remaining-minute",
        "x-rate-limit-remaining-day",
        "retry-after",
    }

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        requests_per_minute: float = 50,
        timeout_seconds: float = 30,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be greater than zero")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.api_key = api_key
        self.max_retries = max_retries
        self._minimum_interval = 60.0 / requests_per_minute
        self._last_request_started: float | None = None
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
            headers={"User-Agent": "dota-predictor/0.1 (personal research project)"},
        )

    def __enter__(self) -> OpenDotaClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        now = time.monotonic()
        if self._last_request_started is not None:
            remaining = self._minimum_interval - (now - self._last_request_started)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_started = time.monotonic()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> ApiResponse[Any]:
        request_params = dict(params or {})
        if self.api_key:
            request_params["api_key"] = self.api_key

        response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                response = self._client.get(path, params=request_params)
            except httpx.TransportError:
                if attempt >= self.max_retries:
                    raise
                time.sleep(min(2**attempt, 20))
                continue

            if response.status_code not in self.RETRYABLE_STATUS_CODES:
                break
            if attempt >= self.max_retries:
                break
            retry_after = response.headers.get("retry-after")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            time.sleep(min(delay, 60))

        if response is None:
            raise RuntimeError("OpenDota request loop completed without a response")
        response.raise_for_status()
        retained_headers = {
            key.lower(): value
            for key, value in response.headers.items()
            if key.lower() in self.RETAINED_HEADERS
        }
        return ApiResponse(
            data=response.json(),
            url=str(response.request.url),
            status_code=response.status_code,
            headers=retained_headers,
            fetched_at=datetime.now(UTC),
        )

    def get_pro_matches(
        self, *, less_than_match_id: int | None = None
    ) -> ApiResponse[list[dict[str, Any]]]:
        params = {"less_than_match_id": less_than_match_id} if less_than_match_id else None
        response = self._get("/proMatches", params)
        if not isinstance(response.data, list):
            raise TypeError("OpenDota /proMatches returned a non-list response")
        return cast(ApiResponse[list[dict[str, Any]]], response)

    def iter_pro_match_pages(self, *, page_count: int, less_than_match_id: int | None = None):
        if page_count < 1:
            raise ValueError("page_count must be at least one")
        cursor = less_than_match_id
        for _ in range(page_count):
            response = self.get_pro_matches(less_than_match_id=cursor)
            yield cursor, response
            match_ids = [int(row["match_id"]) for row in response.data if row.get("match_id")]
            if not match_ids:
                return
            next_cursor = min(match_ids)
            if cursor is not None and next_cursor >= cursor:
                raise RuntimeError("OpenDota pagination cursor did not move backwards")
            cursor = next_cursor

    def get_match(self, match_id: int) -> ApiResponse[dict[str, Any]]:
        response = self._get(f"/matches/{match_id}")
        if not isinstance(response.data, dict):
            raise TypeError(f"OpenDota /matches/{match_id} returned a non-object response")
        return cast(ApiResponse[dict[str, Any]], response)
