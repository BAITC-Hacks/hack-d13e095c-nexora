"""Persist evidence-backed project/document mentions and decisions."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "meetings",
        sa.Column("memory_analysis_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("meetings", sa.Column("memory_attempted_at", sa.DateTime(timezone=True)))
    op.add_column("meetings", sa.Column("memory_error", sa.String(100)))
    op.create_table(
        "memory_occurrences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "meeting_id",
            sa.Uuid(),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("object_key", sa.String(64), nullable=False),
        sa.Column("evidence_key", sa.String(64), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("segment_ids", sa.JSON(), nullable=False),
        sa.Column("url", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("meeting_id", "kind", "object_key", "evidence_key"),
    )
    op.create_index("ix_memory_occurrences_meeting_id", "memory_occurrences", ["meeting_id"])
    op.create_index("ix_memory_occurrences_object_key", "memory_occurrences", ["object_key"])


def downgrade():
    op.drop_table("memory_occurrences")
    op.drop_column("meetings", "memory_error")
    op.drop_column("meetings", "memory_attempted_at")
    op.drop_column("meetings", "memory_analysis_version")
