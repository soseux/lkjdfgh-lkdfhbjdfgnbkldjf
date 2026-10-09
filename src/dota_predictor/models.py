from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Patch(Base):
    __tablename__ = "patches"

    patch_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(String(32))
    release_date: Mapped[date | None] = mapped_column(Date)


class League(Base, TimestampMixin):
    __tablename__ = "leagues"

    league_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[str | None] = mapped_column(String(32))


class Series(Base, TimestampMixin):
    __tablename__ = "series"

    series_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    league_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("leagues.league_id", ondelete="SET NULL")
    )
    series_type: Mapped[int | None] = mapped_column(SmallInteger)


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(Text)
    tag: Mapped[str | None] = mapped_column(String(64))
    logo_url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="opendota")


class TeamAlias(Base):
    __tablename__ = "team_aliases"
    __table_args__ = (UniqueConstraint("team_id", "alias", name="uq_team_alias"),)

    alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Player(Base, TimestampMixin):
    __tablename__ = "players"

    account_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    pro_name: Mapped[str | None] = mapped_column(Text)
    persona_name: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(String(8))
    current_team_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("teams.team_id", ondelete="SET NULL")
    )


class PlayerAlias(Base):
    __tablename__ = "player_aliases"
    __table_args__ = (UniqueConstraint("account_id", "alias", name="uq_player_alias"),)

    alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.account_id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Match(Base, TimestampMixin):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint(
            "ingestion_status IN ('DISCOVERED', 'DETAILS_FETCHED', 'REPLAY_DOWNLOADED', "
            "'PARSED', 'NORMALIZED', 'FEATURES_READY')",
            name="ck_matches_ingestion_status",
        ),
        Index("ix_matches_start_time", "start_time"),
        Index("ix_matches_league_start", "league_id", "start_time"),
    )

    match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    series_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("series.series_id", ondelete="SET NULL")
    )
    league_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("leagues.league_id", ondelete="SET NULL")
    )
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    patch_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("patches.patch_id", ondelete="SET NULL")
    )
    radiant_team_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("teams.team_id", ondelete="SET NULL")
    )
    dire_team_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("teams.team_id", ondelete="SET NULL")
    )
    radiant_win: Mapped[bool | None] = mapped_column(Boolean)
    radiant_first_pick: Mapped[bool | None] = mapped_column(Boolean)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    game_mode: Mapped[int | None] = mapped_column(Integer)
    radiant_score: Mapped[int | None] = mapped_column(Integer)
    dire_score: Mapped[int | None] = mapped_column(Integer)
    ingestion_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DISCOVERED", server_default="DISCOVERED"
    )
    replay_status: Mapped[str | None] = mapped_column(String(32))
    source_version: Mapped[str | None] = mapped_column(String(64))


class TeamRosterPeriod(Base, TimestampMixin):
    __tablename__ = "team_roster_periods"
    __table_args__ = (
        UniqueConstraint("team_id", "account_id", "valid_from", name="uq_team_roster_period_start"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_roster_confidence"),
    )

    roster_period_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.account_id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int | None] = mapped_column(SmallInteger)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class MatchPlayer(Base):
    __tablename__ = "match_players"
    __table_args__ = (
        CheckConstraint("team_side IN ('radiant', 'dire')", name="ck_match_player_side"),
        UniqueConstraint("match_id", "account_id", name="uq_match_player_account"),
    )

    match_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    player_slot: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.account_id", ondelete="SET NULL")
    )
    team_side: Mapped[str] = mapped_column(String(8), nullable=False)
    hero_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[int | None] = mapped_column(SmallInteger)
    lane_role: Mapped[int | None] = mapped_column(SmallInteger)
    is_substitute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DraftAction(Base):
    __tablename__ = "draft_actions"
    __table_args__ = (
        CheckConstraint("team_side IN ('radiant', 'dire')", name="ck_draft_action_side"),
    )

    match_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    sequence_no: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    team_side: Mapped[str] = mapped_column(String(8), nullable=False)
    is_pick: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hero_id: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.account_id", ondelete="SET NULL")
    )


class RawObject(Base):
    __tablename__ = "raw_objects"
    __table_args__ = (
        UniqueConstraint(
            "source", "object_type", "natural_key", "sha256", name="uq_raw_object_version"
        ),
        Index("ix_raw_objects_lookup", "source", "object_type", "natural_key"),
    )

    raw_object_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    natural_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_headers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_version: Mapped[str | None] = mapped_column(String(128))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'retry', 'succeeded', 'dead')",
            name="ck_ingestion_job_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_ingestion_job_attempts"),
        CheckConstraint("max_attempts > 0", name="ck_ingestion_job_max_attempts"),
        Index("ix_ingestion_jobs_claim", "status", "available_at", "priority"),
    )

    job_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    match_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("matches.match_id", ondelete="CASCADE")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(128))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
