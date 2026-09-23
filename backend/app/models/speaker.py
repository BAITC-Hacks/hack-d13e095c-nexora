from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityMixin


class Speaker(IdentityMixin, Base):
    __tablename__ = "speakers"
    __table_args__ = (
        UniqueConstraint("meeting_id", "speaker_id"),
        ForeignKeyConstraint(
            ["meeting_id", "participant_id"],
            ["participants.meeting_id", "participants.id"],
        ),
    )

    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    speaker_id: Mapped[str] = mapped_column(String(64))
    participant_id: Mapped[UUID | None]
