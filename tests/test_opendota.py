import httpx

from dota_predictor.ingestion.opendota import OpenDotaClient


def test_pro_match_pagination_moves_to_oldest_match() -> None:
    requested_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("less_than_match_id")
        requested_cursors.append(cursor)
        body = [{"match_id": 105}, {"match_id": 101}] if cursor is None else [{"match_id": 99}]
        return httpx.Response(200, json=body, headers={"ETag": '"v1"'})

    with OpenDotaClient(
        "https://api.opendota.test/api",
        requests_per_minute=1_000_000_000,
        transport=httpx.MockTransport(handler),
    ) as client:
        pages = list(client.iter_pro_match_pages(page_count=2))

    assert requested_cursors == [None, "101"]
    assert [cursor for cursor, _ in pages] == [None, 101]
    assert pages[0][1].source_version == '"v1"'


def test_api_key_and_match_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/matches/123"
        assert request.url.params["api_key"] == "secret"
        return httpx.Response(200, json={"match_id": 123})

    with OpenDotaClient(
        "https://api.opendota.test/api",
        api_key="secret",
        requests_per_minute=1_000_000_000,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = client.get_match(123)

    assert response.data == {"match_id": 123}
