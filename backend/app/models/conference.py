from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin


class Conference(IdentityMixin, Base):
    __tablename__ = "conferences"
    id: Mapped[UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    baseline_tasks: Mapped[list | None] = mapped_column(JSON)
    invite_hash: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording: Mapped[bool] = mapped_column(Boolean, default=False)
    recording_version: Mapped[int] = mapped_column(Integer, default=0)
    recording_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analysis_cursor: Mapped[int] = mapped_column(Integer, default=-1)
    analysis_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    analysis_status: Mapped[str] = mapped_column(String(32), default="waiting")
    analysis_error: Mapped[str | None] = mapped_column(String(100))
    analysis_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConferenceMember(IdentityMixin, Base):
    __tablename__ = "conference_members"
    id: Mapped[UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), primary_key=True
    )
    conference_id: Mapped[UUID] = mapped_column(
        ForeignKey("conferences.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    is_host: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AudioChunk(IdentityMixin, Base):
    __tablename__ = "conference_audio_chunks"
    __table_args__ = (UniqueConstraint("member_id", "sequence"),)
    conference_id: Mapped[UUID] = mapped_column(
        ForeignKey("conferences.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[UUID] = mapped_column(ForeignKey("conference_members.id", ondelete="CASCADE"))
    sequence: Mapped[str] = mapped_column(String(36))
    start: Mapped[float] = mapped_column(Float)
    duration: Mapped[float] = mapped_column(Float)
    path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(100))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConferenceMessage(IdentityMixin, Base):
    __tablename__ = "conference_messages"
    conference_id: Mapped[UUID] = mapped_column(
        ForeignKey("conferences.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[UUID] = mapped_column(ForeignKey("conference_members.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)


class ConferenceRecording(IdentityMixin, Base):
    __tablename__ = "conference_recordings"
    __table_args__ = (UniqueConstraint("conference_id", "version"),)
    conference_id: Mapped[UUID] = mapped_column(
        ForeignKey("conferences.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
