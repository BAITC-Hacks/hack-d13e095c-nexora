from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import select, update

from app.api.deps import Session
from app.models import Participant, Task
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.participant_repository import ParticipantRepository
from app.schemas.participant import ParticipantCreate, ParticipantPatch, ParticipantRead

router = APIRouter(prefix="/meetings/{meeting_id}/participants", tags=["participants"])


@router.post("", response_model=ParticipantRead, status_code=201)
async def create(meeting_id: UUID, body: ParticipantCreate, session: Session):
    # Adding participants is useful while STT is running; it cannot affect STT results.
    meeting = await MeetingRepository(session).get(meeting_id, lock=True)
    participant = Participant(meeting_id=meeting_id, **body.model_dump())
    session.add(participant)
    meeting.analysis_stale = True
    await session.flush()
    return participant


@router.get("", response_model=list[ParticipantRead])
async def list_participants(meeting_id: UUID, session: Session):
    await MeetingRepository(session).get(meeting_id)
    return (
        await session.scalars(
            select(Participant)
            .where(Participant.meeting_id == meeting_id)
            .order_by(Participant.created_at, Participant.id)
        )
    ).all()


@router.patch("/{participant_id}", response_model=ParticipantRead)
async def patch(meeting_id: UUID, participant_id: UUID, body: ParticipantPatch, session: Session):
    meeting = await MeetingRepository(session).editable(meeting_id)
    participant = await ParticipantRepository(session).get(meeting_id, participant_id)
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(participant, name, value)
    if "name" in body.model_fields_set:
        await session.execute(
            update(Task)
            .where(Task.responsible_participant_id == participant.id)
            .values(responsible_name=participant.name)
        )
    meeting.analysis_stale = True
    await session.flush()
    return participant


@router.delete("/{participant_id}", status_code=204)
async def delete(meeting_id: UUID, participant_id: UUID, session: Session):
    meeting = await MeetingRepository(session).editable(meeting_id)
    participant = await ParticipantRepository(session).get(meeting_id, participant_id)
    await ParticipantRepository(session).delete(participant)
    meeting.analysis_stale = True
    return Response(status_code=204)
