from typing import Any

from sqlalchemy.dialects import postgresql

from dota_predictor.models import DraftAction, MatchPlayer
from dota_predictor.repository import normalize_match_detail


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []
        self.added: list[Any] = []

    def execute(self, statement):
        statement.compile(dialect=postgresql.dialect())
        self.statements.append(statement)
        return None

    def add(self, entity) -> None:
        self.added.append(entity)


def test_match_detail_builds_players_and_ordered_draft() -> None:
    session = RecordingSession()
    payload = {
        "match_id": 123,
        "leagueid": 10,
        "league_name": "Test League",
        "series_id": 20,
        "series_type": 1,
        "start_time": 1_700_000_000,
        "patch": 60,
        "radiant_team_id": 30,
        "radiant_name": "Radiant Test",
        "dire_team_id": 40,
        "dire_name": "Dire Test",
        "radiant_win": True,
        "players": [
            {
                "account_id": 1001,
                "player_slot": 0,
                "hero_id": 1,
                "name": "Carry",
                "personaname": "CarryPersona",
            },
            {
                "account_id": 2001,
                "player_slot": 128,
                "hero_id": 2,
                "name": "Opponent",
            },
        ],
        "picks_bans": [
            {"order": 1, "team": 0, "is_pick": True, "hero_id": 1},
            {"order": 0, "team": 1, "is_pick": False, "hero_id": 2},
        ],
    }

    assert normalize_match_detail(session, payload) == 123

    players = [entity for entity in session.added if isinstance(entity, MatchPlayer)]
    draft = [entity for entity in session.added if isinstance(entity, DraftAction)]
    assert [(player.account_id, player.team_side) for player in players] == [
        (1001, "radiant"),
        (2001, "dire"),
    ]
    assert [(action.sequence_no, action.team_side, action.is_pick) for action in draft] == [
        (0, "dire", False),
        (1, "radiant", True),
    ]
