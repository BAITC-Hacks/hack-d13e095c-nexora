"""Persistent conferences, member capabilities and durable audio queue."""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = depends_on = None


def identity(parent=None):
    return [
        sa.Column(
            "id",
            sa.Uuid(),
            *([sa.ForeignKey(parent, ondelete="CASCADE")] if parent else []),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        "conferences",
        *identity("meetings.id"),
        sa.Column("invite_hash", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("recording", sa.Boolean(), nullable=False),
        sa.Column("recording_version", sa.Integer(), nullable=False),
        sa.Column("recording_started_at", sa.DateTime(timezone=True)),
        sa.Column("recording_stopped_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("analysis_cursor", sa.Integer(), nullable=False),
        sa.Column("analysis_requested", sa.Boolean(), nullable=False),
        sa.Column("analysis_status", sa.String(32), nullable=False),
        sa.Column("analysis_error", sa.String(100)),
        sa.Column("analysis_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "conference_members",
        *identity("participants.id"),
        sa.Column(
            "conference_id",
            sa.Uuid(),
            sa.ForeignKey("conferences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("is_host", sa.Boolean(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conference_members_conference_id", "conference_members", ["conference_id"])
    op.create_table(
        "conference_audio_chunks",
        *identity(),
        sa.Column(
            "conference_id",
            sa.Uuid(),
            sa.ForeignKey("conferences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.Uuid(),
            sa.ForeignKey("conference_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.String(36), nullable=False),
        sa.Column("start", sa.Float(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(100)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("member_id", "sequence"),
    )
    op.create_index(
        "ix_conference_audio_chunks_conference_id", "conference_audio_chunks", ["conference_id"]
    )
    op.create_index("ix_conference_audio_chunks_status", "conference_audio_chunks", ["status"])
    op.create_table(
        "conference_messages",
        *identity(),
        sa.Column(
            "conference_id",
            sa.Uuid(),
            sa.ForeignKey("conferences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.Uuid(),
            sa.ForeignKey("conference_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_conference_messages_conference_id", "conference_messages", ["conference_id"]
    )

    op.create_table(
        "conference_recordings",
        *identity(),
        sa.Column(
            "conference_id",
            sa.Uuid(),
            sa.ForeignKey("conferences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("conference_id", "version"),
    )
    op.create_index(
        "ix_conference_recordings_conference_id", "conference_recordings", ["conference_id"]
    )


def downgrade():
    for table in (
        "conference_recordings",
        "conference_messages",
        "conference_audio_chunks",
        "conference_members",
        "conferences",
    ):
        op.drop_table(table)
