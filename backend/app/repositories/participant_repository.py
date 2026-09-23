from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Participant, Speaker, Task


class ParticipantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, meeting_id: UUID, participant_id: UUID) -> Participant:
        participant = await self.session.scalar(
            select(Participant).where(
                Participant.id == participant_id,
                Participant.meeting_id == meeting_id,
            )
        )
        if participant is None:
            raise HTTPException(404, "Participant not found in this meeting")
        return participant

    async def delete(self, participant: Participant):
        await self.session.execute(
            update(Speaker)
            .where(Speaker.participant_id == participant.id)
            .values(participant_id=None)
        )
        await self.session.execute(
            update(Task)
            .where(Task.responsible_participant_id == participant.id)
            .values(
                responsible_participant_id=None,
                responsible_name=None,
                responsible_speaker_id=None,
            )
        )
        await self.session.delete(participant)
