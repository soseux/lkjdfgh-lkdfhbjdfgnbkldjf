from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def positive_id(value: Any) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def unix_datetime(value: Any) -> datetime | None:
    if value in (None, 0, "0"):
        return None
    return datetime.fromtimestamp(int(value), tz=UTC)


def side_from_player_slot(player_slot: int) -> str:
    return "dire" if int(player_slot) >= 128 else "radiant"


def side_from_draft_team(team: int) -> str:
    if int(team) == 0:
        return "radiant"
    if int(team) == 1:
        return "dire"
    raise ValueError(f"Unknown OpenDota draft team: {team}")


def infer_radiant_first_pick(picks_bans: list[dict[str, Any]] | None) -> bool | None:
    actions = sorted(picks_bans or [], key=lambda item: int(item.get("order", 0)))
    first_pick = next((item for item in actions if item.get("is_pick") is True), None)
    if first_pick is None or first_pick.get("team") not in (0, 1):
        return None
    return int(first_pick["team"]) == 0
