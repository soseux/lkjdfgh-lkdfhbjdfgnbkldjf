"""Initial ingestion schema.

Revision ID: 0001
Revises: None
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patches",
        sa.Column("patch_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(length=32)),
        sa.Column("release_date", sa.Date()),
    )
    op.create_table(
        "leagues",
        sa.Column("league_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text()),
        sa.Column("tier", sa.String(length=32)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "teams",
        sa.Column("team_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text()),
        sa.Column("tag", sa.String(length=64)),
        sa.Column("logo_url", sa.Text()),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "series",
        sa.Column("series_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column(
            "league_id", sa.BigInteger(), sa.ForeignKey("leagues.league_id", ondelete="SET NULL")
        ),
        sa.Column("series_type", sa.SmallInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "team_aliases",
        sa.Column("alias_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.team_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("team_id", "alias", name="uq_team_alias"),
    )
    op.create_table(
        "players",
        sa.Column("account_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("pro_name", sa.Text()),
        sa.Column("persona_name", sa.Text()),
        sa.Column("country_code", sa.String(length=8)),
        sa.Column(
            "current_team_id", sa.BigInteger(), sa.ForeignKey("teams.team_id", ondelete="SET NULL")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "player_aliases",
        sa.Column("alias_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("players.account_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("account_id", "alias", name="uq_player_alias"),
    )
    op.create_table(
        "matches",
        sa.Column("match_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column(
            "series_id", sa.BigInteger(), sa.ForeignKey("series.series_id", ondelete="SET NULL")
        ),
        sa.Column(
            "league_id", sa.BigInteger(), sa.ForeignKey("leagues.league_id", ondelete="SET NULL")
        ),
        sa.Column("start_time", sa.DateTime(timezone=True)),
        sa.Column("patch_id", sa.Integer(), sa.ForeignKey("patches.patch_id", ondelete="SET NULL")),
        sa.Column(
            "radiant_team_id", sa.BigInteger(), sa.ForeignKey("teams.team_id", ondelete="SET NULL")
        ),
        sa.Column(
            "dire_team_id", sa.BigInteger(), sa.ForeignKey("teams.team_id", ondelete="SET NULL")
        ),
        sa.Column("radiant_win", sa.Boolean()),
        sa.Column("radiant_first_pick", sa.Boolean()),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("game_mode", sa.Integer()),
        sa.Column("radiant_score", sa.Integer()),
        sa.Column("dire_score", sa.Integer()),
        sa.Column(
            "ingestion_status", sa.String(length=32), server_default="DISCOVERED", nullable=False
        ),
        sa.Column("replay_status", sa.String(length=32)),
        sa.Column("source_version", sa.String(length=64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "ingestion_status IN ('DISCOVERED', 'DETAILS_FETCHED', 'REPLAY_DOWNLOADED', "
            "'PARSED', 'NORMALIZED', 'FEATURES_READY')",
            name="ck_matches_ingestion_status",
        ),
    )
    op.create_index("ix_matches_start_time", "matches", ["start_time"])
    op.create_index("ix_matches_league_start", "matches", ["league_id", "start_time"])
    op.create_table(
        "team_roster_periods",
        sa.Column("roster_period_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.team_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.BigInteger(),
            sa.ForeignKey("players.account_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger()),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_roster_confidence"),
        sa.UniqueConstraint(
            "team_id", "account_id", "valid_from", name="uq_team_roster_period_start"
        ),
    )
    op.create_table(
        "match_players",
        sa.Column(
            "match_id",
            sa.BigInteger(),
            sa.ForeignKey("matches.match_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("player_slot", sa.SmallInteger(), primary_key=True),
        sa.Column(
            "account_id", sa.BigInteger(), sa.ForeignKey("players.account_id", ondelete="SET NULL")
        ),
        sa.Column("team_side", sa.String(length=8), nullable=False),
        sa.Column("hero_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.SmallInteger()),
        sa.Column("lane_role", sa.SmallInteger()),
        sa.Column("is_substitute", sa.Boolean(), nullable=False),
        sa.CheckConstraint("team_side IN ('radiant', 'dire')", name="ck_match_player_side"),
        sa.UniqueConstraint("match_id", "account_id", name="uq_match_player_account"),
    )
    op.create_table(
        "draft_actions",
        sa.Column(
            "match_id",
            sa.BigInteger(),
            sa.ForeignKey("matches.match_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("sequence_no", sa.SmallInteger(), primary_key=True),
        sa.Column("team_side", sa.String(length=8), nullable=False),
        sa.Column("is_pick", sa.Boolean(), nullable=False),
        sa.Column("hero_id", sa.Integer(), nullable=False),
        sa.Column(
            "player_id", sa.BigInteger(), sa.ForeignKey("players.account_id", ondelete="SET NULL")
        ),
        sa.CheckConstraint("team_side IN ('radiant', 'dire')", name="ck_draft_action_side"),
    )
    op.create_table(
        "raw_objects",
        sa.Column("raw_object_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("natural_key", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("response_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_version", sa.String(length=128)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source", "object_type", "natural_key", "sha256", name="uq_raw_object_version"
        ),
    )
    op.create_index(
        "ix_raw_objects_lookup", "raw_objects", ["source", "object_type", "natural_key"]
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column(
            "match_id", sa.BigInteger(), sa.ForeignKey("matches.match_id", ondelete="CASCADE")
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("worker_id", sa.String(length=128)),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'retry', 'succeeded', 'dead')",
            name="ck_ingestion_job_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_ingestion_job_attempts"),
        sa.CheckConstraint("max_attempts > 0", name="ck_ingestion_job_max_attempts"),
    )
    op.create_index(
        "ix_ingestion_jobs_claim",
        "ingestion_jobs",
        ["status", "available_at", "priority"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_claim", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_raw_objects_lookup", table_name="raw_objects")
    op.drop_table("raw_objects")
    op.drop_table("draft_actions")
    op.drop_table("match_players")
    op.drop_table("team_roster_periods")
    op.drop_index("ix_matches_league_start", table_name="matches")
    op.drop_index("ix_matches_start_time", table_name="matches")
    op.drop_table("matches")
    op.drop_table("player_aliases")
    op.drop_table("players")
    op.drop_table("team_aliases")
    op.drop_table("series")
    op.drop_table("teams")
    op.drop_table("leagues")
    op.drop_table("patches")
