from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin, utcnow
from app.models.enums import MeetingStatus


class Meeting(IdentityMixin, Base):
    __tablename__ = "meetings"

    title: Mapped[str] = mapped_column(String(300))
    meeting_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[MeetingStatus] = mapped_column(Enum(MeetingStatus), default=MeetingStatus.QUEUED)
    stage: Mapped[str] = mapped_column(String(64), default="QUEUED")
    original_path: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    detected_language: Mapped[str | None] = mapped_column(String(20))
    processing_time: Mapped[float | None] = mapped_column(Float)
    stt_model: Mapped[str | None] = mapped_column(String(100))
    duration: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[list] = mapped_column(JSON, default=list)
    decisions: Mapped[list] = mapped_column(JSON, default=list)
    analysis_stale: Mapped[bool] = mapped_column(Boolean, default=True)
    analysis_version: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
