from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin


class MemoryOccurrence(IdentityMixin, Base):
    """A supported mention, scoped to its original meeting; never a model-only edge."""

    __tablename__ = "memory_occurrences"
    __table_args__ = (UniqueConstraint("meeting_id", "kind", "object_key", "evidence_key"),)
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str] = mapped_column(String(64), index=True)
    evidence_key: Mapped[str] = mapped_column(String(64))
    quote: Mapped[str] = mapped_column(Text)
    segment_ids: Mapped[list] = mapped_column(JSON)
    url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
