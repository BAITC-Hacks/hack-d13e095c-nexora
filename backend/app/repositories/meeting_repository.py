from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, Meeting, Participant, Speaker, TranscriptSegment
from app.models.enums import JobKind, JobStatus, MeetingStatus


class MeetingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, meeting_id: UUID, *, lock: bool = False) -> Meeting:
        query = select(Meeting).where(Meeting.id == meeting_id)
        if lock:
            query = query.with_for_update()
        meeting = await self.session.scalar(query)
        if not meeting:
            raise HTTPException(404, "Meeting not found")
        return meeting

    async def editable(self, meeting_id: UUID) -> Meeting:
        meeting = await self.get(meeting_id, lock=True)
        active = await self.session.scalar(
            select(Job.id).where(
                Job.meeting_id == meeting_id,
                Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
            )
        )
        if active:
            raise HTTPException(409, "Meeting has an active job; wait until processing finishes")
        return meeting

    async def enqueue(self, meeting_id: UUID, kind: JobKind, allow_unmapped: bool = False) -> Job:
        meeting = await self.editable(meeting_id)
        if kind == JobKind.TRANSCRIBE:
            existing = await self.session.scalar(
                select(TranscriptSegment.id)
                .where(TranscriptSegment.meeting_id == meeting_id)
                .limit(1)
            )
            if existing or meeting.status != MeetingStatus.FAILED or meeting.analysis_version:
                raise HTTPException(
                    409, "Transcript already exists; use analyze without rerunning speech models"
                )
            meeting.status = MeetingStatus.QUEUED
        else:
            transcript = await self.session.scalar(
                select(TranscriptSegment.id)
                .where(TranscriptSegment.meeting_id == meeting_id)
                .limit(1)
            )
            if transcript is None and meeting.status != MeetingStatus.AWAITING_MAPPING:
                raise HTTPException(409, "Transcription must finish first")
            if not allow_unmapped:
                unmapped = await self.session.scalar(
                    select(Speaker.id)
                    .where(Speaker.meeting_id == meeting_id, Speaker.participant_id.is_(None))
                    .limit(1)
                )
                if unmapped:
                    raise HTTPException(
                        409, "Map speakers first or explicitly set allow_unmapped=true"
                    )
            meeting.status = MeetingStatus.ANALYZING
        meeting.error_code = None
        meeting.stage = "QUEUED_" + kind.value
        job = Job(meeting_id=meeting_id, kind=kind, allow_unmapped=allow_unmapped)
        self.session.add(job)
        await self.session.flush()
        return job

    async def transcript(self, meeting_id: UUID) -> list[dict]:
        query = (
            select(TranscriptSegment, Participant.name)
            .outerjoin(
                Speaker,
                (Speaker.meeting_id == TranscriptSegment.meeting_id)
                & (Speaker.speaker_id == TranscriptSegment.speaker_id),
            )
            .outerjoin(Participant, Participant.id == Speaker.participant_id)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.ordinal)
        )
        rows = (await self.session.execute(query)).all()
        return [
            {
                "id": segment.id,
                "ordinal": segment.ordinal,
                "speaker_id": segment.speaker_id,
                "speaker_name": name,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            }
            for segment, name in rows
        ]
