import json

from dota_predictor.ingestion.raw_store import RawStore


def test_raw_store_is_content_addressed_and_deterministic(tmp_path) -> None:
    store = RawStore(tmp_path)
    first = store.write_json(
        source="opendota",
        object_type="matches",
        natural_key="123",
        data={"b": 2, "a": 1},
    )
    second = store.write_json(
        source="opendota",
        object_type="matches",
        natural_key="123",
        data={"a": 1, "b": 2},
    )

    assert first == second
    assert first.path.is_file()
    assert json.loads(first.path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert len(list((tmp_path / "opendota" / "matches" / "123").glob("*.json"))) == 1


def test_raw_store_sanitizes_path_components(tmp_path) -> None:
    stored = RawStore(tmp_path).write_json(
        source="open/dota",
        object_type="pro matches",
        natural_key="../latest",
        data=[],
    )
    assert stored.path.is_relative_to(tmp_path)
    assert ".." not in stored.path.parts
