"""Durable pre-meeting briefings and immutable task state at meeting close."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None


def upgrade():
    op.add_column("conferences", sa.Column("baseline_tasks", sa.JSON(), nullable=True))
    op.create_table(
        "conference_briefings",
        sa.Column(
            "id", sa.Uuid(), sa.ForeignKey("conferences.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_id", sa.Uuid(), sa.ForeignKey("conferences.id", ondelete="SET NULL")),
        sa.Column("updates", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("input_hash", sa.String(64)),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.String(100)),
    )


def downgrade():
    op.drop_table("conference_briefings")
    op.drop_column("conferences", "baseline_tasks")
