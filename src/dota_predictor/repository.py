from __future__ import annotations

from typing import Any

from sqlalchemy import case, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from dota_predictor.ingestion.normalizer import (
    infer_radiant_first_pick,
    optional_int,
    positive_id,
    side_from_draft_team,
    side_from_player_slot,
    unix_datetime,
)
from dota_predictor.ingestion.opendota import ApiResponse
from dota_predictor.ingestion.raw_store import StoredObject
from dota_predictor.models import (
    DraftAction,
    League,
    Match,
    MatchPlayer,
    Patch,
    Player,
    PlayerAlias,
    RawObject,
    Series,
    Team,
    TeamAlias,
)

ANONYMOUS_ACCOUNT_ID = 4_294_967_295


def _account_id(value: Any) -> int | None:
    parsed = positive_id(value)
    return None if parsed == ANONYMOUS_ACCOUNT_ID else parsed


def _upsert_league(session: Session, league_id: int | None, name: str | None) -> None:
    if league_id is None:
        return
    statement = insert(League).values(league_id=league_id, name=name)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[League.league_id],
            set_={
                "name": func.coalesce(statement.excluded.name, League.name),
                "updated_at": func.now(),
            },
        )
    )


def _upsert_series(
    session: Session,
    series_id: int | None,
    league_id: int | None,
    series_type: int | None,
) -> None:
    if series_id is None:
        return
    statement = insert(Series).values(
        series_id=series_id, league_id=league_id, series_type=series_type
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[Series.series_id],
            set_={
                "league_id": func.coalesce(statement.excluded.league_id, Series.league_id),
                "series_type": func.coalesce(statement.excluded.series_type, Series.series_type),
                "updated_at": func.now(),
            },
        )
    )


def _upsert_team(
    session: Session,
    team_id: int | None,
    *,
    name: str | None,
    tag: str | None = None,
    logo_url: str | None = None,
) -> None:
    if team_id is None:
        return
    statement = insert(Team).values(
        team_id=team_id,
        name=name,
        tag=tag,
        logo_url=logo_url,
        source="opendota",
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[Team.team_id],
            set_={
                "name": func.coalesce(statement.excluded.name, Team.name),
                "tag": func.coalesce(statement.excluded.tag, Team.tag),
                "logo_url": func.coalesce(statement.excluded.logo_url, Team.logo_url),
                "updated_at": func.now(),
            },
        )
    )
    if name:
        session.execute(
            insert(TeamAlias)
            .values(team_id=team_id, alias=name)
            .on_conflict_do_nothing(constraint="uq_team_alias")
        )


def _team_fields(payload: dict[str, Any], side: str) -> tuple[int | None, dict[str, Any]]:
    nested = payload.get(f"{side}_team")
    team = nested if isinstance(nested, dict) else {}
    team_id = positive_id(payload.get(f"{side}_team_id") or team.get("team_id"))
    return team_id, {
        "name": payload.get(f"{side}_name") or team.get("name"),
        "tag": team.get("tag"),
        "logo_url": team.get("logo_url"),
    }


def upsert_pro_match_summaries(session: Session, summaries: list[dict[str, Any]]) -> list[int]:
    match_ids: list[int] = []
    for summary in summaries:
        match_id = positive_id(summary.get("match_id"))
        if match_id is None:
            continue
        league_id = positive_id(summary.get("leagueid"))
        series_id = positive_id(summary.get("series_id"))
        radiant_team_id, radiant_team = _team_fields(summary, "radiant")
        dire_team_id, dire_team = _team_fields(summary, "dire")

        _upsert_league(session, league_id, summary.get("league_name"))
        _upsert_series(session, series_id, league_id, summary.get("series_type"))
        _upsert_team(session, radiant_team_id, **radiant_team)
        _upsert_team(session, dire_team_id, **dire_team)

        statement = insert(Match).values(
            match_id=match_id,
            series_id=series_id,
            league_id=league_id,
            start_time=unix_datetime(summary.get("start_time")),
            radiant_team_id=radiant_team_id,
            dire_team_id=dire_team_id,
            radiant_win=summary.get("radiant_win"),
            duration_seconds=summary.get("duration"),
            radiant_score=summary.get("radiant_score"),
            dire_score=summary.get("dire_score"),
            ingestion_status="DISCOVERED",
            source_version=(
                str(summary["version"]) if summary.get("version") is not None else None
            ),
        )
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[Match.match_id],
                set_={
                    "series_id": func.coalesce(statement.excluded.series_id, Match.series_id),
                    "league_id": func.coalesce(statement.excluded.league_id, Match.league_id),
                    "start_time": func.coalesce(statement.excluded.start_time, Match.start_time),
                    "radiant_team_id": func.coalesce(
                        statement.excluded.radiant_team_id, Match.radiant_team_id
                    ),
                    "dire_team_id": func.coalesce(
                        statement.excluded.dire_team_id, Match.dire_team_id
                    ),
                    "radiant_win": func.coalesce(statement.excluded.radiant_win, Match.radiant_win),
                    "duration_seconds": func.coalesce(
                        statement.excluded.duration_seconds, Match.duration_seconds
                    ),
                    "radiant_score": func.coalesce(
                        statement.excluded.radiant_score, Match.radiant_score
                    ),
                    "dire_score": func.coalesce(statement.excluded.dire_score, Match.dire_score),
                    "source_version": func.coalesce(
                        statement.excluded.source_version, Match.source_version
                    ),
                    "updated_at": func.now(),
                },
            )
        )
        match_ids.append(match_id)
    return match_ids


def normalize_match_detail(session: Session, payload: dict[str, Any]) -> int:
    match_id = positive_id(payload.get("match_id"))
    if match_id is None:
        raise ValueError("OpenDota match response has no valid match_id")

    league = payload.get("league") if isinstance(payload.get("league"), dict) else {}
    league_id = positive_id(
        payload.get("leagueid") or league.get("leagueid") or league.get("league_id")
    )
    series_id = positive_id(payload.get("series_id"))
    patch_id = positive_id(payload.get("patch"))
    radiant_team_id, radiant_team = _team_fields(payload, "radiant")
    dire_team_id, dire_team = _team_fields(payload, "dire")

    _upsert_league(session, league_id, payload.get("league_name") or league.get("name"))
    _upsert_series(session, series_id, league_id, payload.get("series_type"))
    _upsert_team(session, radiant_team_id, **radiant_team)
    _upsert_team(session, dire_team_id, **dire_team)
    if patch_id is not None:
        session.execute(insert(Patch).values(patch_id=patch_id).on_conflict_do_nothing())

    picks_bans = payload.get("picks_bans")
    picks_bans = picks_bans if isinstance(picks_bans, list) else []
    source_version = payload.get("version")
    statement = insert(Match).values(
        match_id=match_id,
        series_id=series_id,
        league_id=league_id,
        start_time=unix_datetime(payload.get("start_time")),
        patch_id=patch_id,
        radiant_team_id=radiant_team_id,
        dire_team_id=dire_team_id,
        radiant_win=payload.get("radiant_win"),
        radiant_first_pick=infer_radiant_first_pick(picks_bans),
        duration_seconds=payload.get("duration"),
        game_mode=payload.get("game_mode"),
        radiant_score=payload.get("radiant_score"),
        dire_score=payload.get("dire_score"),
        ingestion_status="DETAILS_FETCHED",
        source_version=str(source_version) if source_version is not None else None,
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[Match.match_id],
            set_={
                "series_id": func.coalesce(statement.excluded.series_id, Match.series_id),
                "league_id": func.coalesce(statement.excluded.league_id, Match.league_id),
                "start_time": func.coalesce(statement.excluded.start_time, Match.start_time),
                "patch_id": func.coalesce(statement.excluded.patch_id, Match.patch_id),
                "radiant_team_id": func.coalesce(
                    statement.excluded.radiant_team_id, Match.radiant_team_id
                ),
                "dire_team_id": func.coalesce(statement.excluded.dire_team_id, Match.dire_team_id),
                "radiant_win": func.coalesce(statement.excluded.radiant_win, Match.radiant_win),
                "radiant_first_pick": func.coalesce(
                    statement.excluded.radiant_first_pick, Match.radiant_first_pick
                ),
                "duration_seconds": func.coalesce(
                    statement.excluded.duration_seconds, Match.duration_seconds
                ),
                "game_mode": func.coalesce(statement.excluded.game_mode, Match.game_mode),
                "radiant_score": func.coalesce(
                    statement.excluded.radiant_score, Match.radiant_score
                ),
                "dire_score": func.coalesce(statement.excluded.dire_score, Match.dire_score),
                "source_version": func.coalesce(
                    statement.excluded.source_version, Match.source_version
                ),
                "ingestion_status": case(
                    (Match.ingestion_status == "DISCOVERED", "DETAILS_FETCHED"),
                    else_=Match.ingestion_status,
                ),
                "updated_at": func.now(),
            },
        )
    )

    players = payload.get("players")
    if isinstance(players, list) and players:
        session.execute(delete(MatchPlayer).where(MatchPlayer.match_id == match_id))
        for player_payload in players:
            if not isinstance(player_payload, dict) or player_payload.get("player_slot") is None:
                continue
            slot = int(player_payload["player_slot"])
            side = side_from_player_slot(slot)
            account_id = _account_id(player_payload.get("account_id"))
            side_team_id = radiant_team_id if side == "radiant" else dire_team_id
            player_team_id = positive_id(player_payload.get("team_id")) or side_team_id
            if account_id is not None:
                player_statement = insert(Player).values(
                    account_id=account_id,
                    pro_name=player_payload.get("name"),
                    persona_name=player_payload.get("personaname"),
                    country_code=player_payload.get("country_code"),
                    current_team_id=player_team_id,
                )
                session.execute(
                    player_statement.on_conflict_do_update(
                        index_elements=[Player.account_id],
                        set_={
                            "pro_name": func.coalesce(
                                player_statement.excluded.pro_name, Player.pro_name
                            ),
                            "persona_name": func.coalesce(
                                player_statement.excluded.persona_name, Player.persona_name
                            ),
                            "country_code": func.coalesce(
                                player_statement.excluded.country_code, Player.country_code
                            ),
                            "current_team_id": func.coalesce(
                                player_statement.excluded.current_team_id,
                                Player.current_team_id,
                            ),
                            "updated_at": func.now(),
                        },
                    )
                )
                for alias in {player_payload.get("name"), player_payload.get("personaname")} - {
                    None,
                    "",
                }:
                    session.execute(
                        insert(PlayerAlias)
                        .values(account_id=account_id, alias=alias)
                        .on_conflict_do_nothing(constraint="uq_player_alias")
                    )

            session.add(
                MatchPlayer(
                    match_id=match_id,
                    player_slot=slot,
                    account_id=account_id,
                    team_side=side,
                    hero_id=int(player_payload.get("hero_id") or 0),
                    role=optional_int(player_payload.get("position")),
                    lane_role=optional_int(player_payload.get("lane_role")),
                    is_substitute=bool(player_payload.get("is_substitute", False)),
                )
            )

    if picks_bans:
        session.execute(delete(DraftAction).where(DraftAction.match_id == match_id))
        for offset, action in enumerate(
            sorted(picks_bans, key=lambda item: int(item.get("order", 0)))
        ):
            if action.get("team") not in (0, 1) or not action.get("hero_id"):
                continue
            session.add(
                DraftAction(
                    match_id=match_id,
                    sequence_no=int(action.get("order", offset)),
                    team_side=side_from_draft_team(action["team"]),
                    is_pick=bool(action.get("is_pick")),
                    hero_id=int(action["hero_id"]),
                    player_id=_account_id(action.get("player_id")),
                )
            )

    return match_id


def register_raw_object(
    session: Session,
    *,
    source: str,
    object_type: str,
    natural_key: str,
    response: ApiResponse[Any],
    stored: StoredObject,
) -> None:
    session.execute(
        insert(RawObject)
        .values(
            source=source,
            object_type=object_type,
            natural_key=natural_key,
            source_url=response.url,
            storage_path=str(stored.path),
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            http_status=response.status_code,
            response_headers=response.headers,
            source_version=response.source_version,
            fetched_at=response.fetched_at,
        )
        .on_conflict_do_nothing(constraint="uq_raw_object_version")
    )
