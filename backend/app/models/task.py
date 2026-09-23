from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, utcnow
from app.models.enums import Priority, TaskStatus


class Task(IdentityMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["meeting_id", "responsible_participant_id"],
            ["participants.meeting_id", "participants.id"],
        ),
        UniqueConstraint("meeting_id", "extraction_key"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="valid_confidence"),
    )

    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    responsible_participant_id: Mapped[UUID | None] = mapped_column(index=True)
    responsible_name: Mapped[str | None] = mapped_column(Text)
    responsible_speaker_id: Mapped[str | None] = mapped_column(String(64))
    assigned_by: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deadline_raw: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.NEW, index=True)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.normal)
    confidence: Mapped[float] = mapped_column(Float)
    source_transcript_start: Mapped[float | None] = mapped_column(Float)
    source_transcript_end: Mapped[float | None] = mapped_column(Float)
    source_quote: Mapped[str] = mapped_column(Text)
    extraction_key: Mapped[str] = mapped_column(String(64))
    analysis_version: Mapped[int] = mapped_column(Integer)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
