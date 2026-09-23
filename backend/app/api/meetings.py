from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Query, UploadFile
from sqlalchemy import select

from app.api.deps import Config, Session
from app.models import Job, Meeting
from app.models.enums import JobKind
from app.repositories.meeting_repository import MeetingRepository
from app.schemas.meeting import AnalyzeRequest, JobRead, MeetingCreate, MeetingRead
from app.schemas.participant import SpeakerPatch, SpeakerRead
from app.schemas.transcript import TranscriptRead
from app.services.speaker_service import SpeakerService
from app.utils.files import save_upload

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.post("", response_model=MeetingRead, status_code=202)
async def upload_meeting(
    session: Session,
    settings: Config,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=300)],
    meeting_date: Annotated[str, Form()],
    timezone: Annotated[str | None, Form()] = None,
):
    from fastapi.exceptions import RequestValidationError
    from pydantic import ValidationError

    try:
        metadata = MeetingCreate(
            title=title, meeting_date=meeting_date, timezone=timezone or settings.meeting_timezone
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    meeting_id = uuid4()
    path, size, filename = await save_upload(file, meeting_id, settings)
    try:
        meeting = Meeting(
            id=meeting_id,
            **metadata.model_dump(),
            original_path=str(path),
            original_filename=filename,
            file_size=size,
            mime_type=file.content_type or "",
        )
        session.add(meeting)
        session.add(Job(meeting_id=meeting_id, kind=JobKind.TRANSCRIBE))
        # Explicit flush ordering without ORM relationships.
        await session.flush([meeting])
        await session.commit()
        return meeting
    except BaseException:
        path.unlink(missing_ok=True)
        raise


@router.get("", response_model=list[MeetingRead])
async def list_meetings(
    session: Session, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)
):
    return (
        await session.scalars(
            select(Meeting)
            .order_by(Meeting.created_at.desc(), Meeting.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()


@router.get("/{meeting_id}", response_model=MeetingRead)
async def get_meeting(meeting_id: UUID, session: Session):
    return await MeetingRepository(session).get(meeting_id)


@router.get("/{meeting_id}/jobs", response_model=list[JobRead])
async def get_jobs(meeting_id: UUID, session: Session):
    await MeetingRepository(session).get(meeting_id)
    return (
        await session.scalars(
            select(Job)
            .where(Job.meeting_id == meeting_id)
            .order_by(Job.created_at.desc())
            .limit(100)
        )
    ).all()


@router.post("/{meeting_id}/process", response_model=JobRead, status_code=202)
async def retry_transcription(meeting_id: UUID, session: Session):
    return await MeetingRepository(session).enqueue(meeting_id, JobKind.TRANSCRIBE)


@router.post("/{meeting_id}/analyze", response_model=JobRead, status_code=202)
async def analyze(meeting_id: UUID, body: AnalyzeRequest, session: Session):
    return await MeetingRepository(session).enqueue(
        meeting_id, JobKind.ANALYZE, body.allow_unmapped
    )


@router.get("/{meeting_id}/transcript", response_model=list[TranscriptRead])
async def transcript(meeting_id: UUID, session: Session):
    await MeetingRepository(session).get(meeting_id)
    return await MeetingRepository(session).transcript(meeting_id)


@router.get("/{meeting_id}/speakers", response_model=list[SpeakerRead])
async def speakers(meeting_id: UUID, session: Session):
    await MeetingRepository(session).get(meeting_id)
    return await SpeakerService(session).list(meeting_id)


@router.patch("/{meeting_id}/speakers/{speaker_id}", response_model=SpeakerRead)
async def map_speaker(meeting_id: UUID, speaker_id: str, body: SpeakerPatch, session: Session):
    return await SpeakerService(session).map(meeting_id, speaker_id, body.participant_id)
