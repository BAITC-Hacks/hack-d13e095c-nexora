from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin


class ConferenceBriefing(IdentityMixin, Base):
    __tablename__ = "conference_briefings"
    id: Mapped[UUID] = mapped_column(
        ForeignKey("conferences.id", ondelete="CASCADE"), primary_key=True
    )
    previous_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conferences.id", ondelete="SET NULL")
    )
    updates: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(100))
