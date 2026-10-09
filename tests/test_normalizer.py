from datetime import UTC, datetime

import pytest

from dota_predictor.ingestion.normalizer import (
    infer_radiant_first_pick,
    optional_int,
    positive_id,
    side_from_draft_team,
    side_from_player_slot,
    unix_datetime,
)


def test_ids_and_timestamp_are_normalized() -> None:
    assert positive_id("123") == 123
    assert positive_id(0) is None
    assert optional_int("3") == 3
    assert optional_int(None) is None
    assert unix_datetime(1_700_000_000) == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_player_slot_maps_to_team_side() -> None:
    assert side_from_player_slot(0) == "radiant"
    assert side_from_player_slot(4) == "radiant"
    assert side_from_player_slot(128) == "dire"
    assert side_from_player_slot(132) == "dire"


def test_draft_team_and_first_pick_are_normalized() -> None:
    draft = [
        {"order": 3, "team": 0, "is_pick": True, "hero_id": 1},
        {"order": 0, "team": 1, "is_pick": False, "hero_id": 2},
        {"order": 2, "team": 1, "is_pick": True, "hero_id": 3},
    ]
    assert side_from_draft_team(0) == "radiant"
    assert side_from_draft_team(1) == "dire"
    assert infer_radiant_first_pick(draft) is False
    assert infer_radiant_first_pick([]) is None
    with pytest.raises(ValueError):
        side_from_draft_team(2)
