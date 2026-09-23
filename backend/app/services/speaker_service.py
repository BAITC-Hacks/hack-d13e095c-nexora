from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Participant, Speaker, Task
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.participant_repository import ParticipantRepository


class SpeakerService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, meeting_id: UUID) -> list[dict]:
        rows = (
            await self.session.execute(
                select(Speaker, Participant.name)
                .outerjoin(Participant, Participant.id == Speaker.participant_id)
                .where(Speaker.meeting_id == meeting_id)
                .order_by(Speaker.speaker_id)
            )
        ).all()
        return [
            {
                "speaker_id": speaker.speaker_id,
                "participant_id": speaker.participant_id,
                "speaker_name": name,
            }
            for speaker, name in rows
        ]

    async def map(self, meeting_id: UUID, speaker_id: str, participant_id: UUID | None) -> dict:
        meeting = await MeetingRepository(self.session).editable(meeting_id)
        speaker = await self.session.scalar(
            select(Speaker).where(
                Speaker.meeting_id == meeting_id, Speaker.speaker_id == speaker_id
            )
        )
        if speaker is None:
            raise HTTPException(404, "Speaker not found")
        participant = (
            await ParticipantRepository(self.session).get(meeting_id, participant_id)
            if participant_id
            else None
        )
        if speaker_id == "UNKNOWN" and participant:
            raise HTTPException(422, "UNKNOWN can contain multiple people and cannot be mapped")
        speaker.participant_id = participant_id
        meeting.analysis_stale = True
        # Preserve explicit human corrections; propagate only machine-derived assignments.
        await self.session.execute(
            update(Task)
            .where(
                Task.meeting_id == meeting_id,
                Task.responsible_speaker_id == speaker_id,
                Task.edited_by_user.is_(False),
            )
            .values(
                responsible_participant_id=participant_id,
                responsible_name=participant.name if participant else None,
            )
        )
        return {
            "speaker_id": speaker_id,
            "participant_id": participant_id,
            "speaker_name": participant.name if participant else None,
        }
