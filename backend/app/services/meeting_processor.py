import asyncio
from uuid import UUID

from sqlalchemy import delete, select

from app.config import Settings
from app.models import Participant, Speaker, Task, TranscriptSegment
from app.models.enums import JobKind, MeetingStatus, Priority
from app.repositories.meeting_repository import MeetingRepository
from app.services.audio_service import AudioService
from app.services.diarization_service import DiarizationService
from app.services.job_service import JobService
from app.services.llm_service import LLMService
from app.services.summary_service import SummaryService
from app.services.task_extraction_service import TaskExtractionService, extraction_key, normalized
from app.services.transcript_merge_service import TranscriptMergeService
from app.services.transcription_service import TranscriptionService
from app.utils.dates import end_of_day
from app.utils.files import meeting_directory


class MeetingProcessor:
    def __init__(
        self,
        factory,
        settings: Settings,
        *,
        audio=None,
        transcription=None,
        diarization=None,
        llm=None,
    ):
        self.factory, self.settings = factory, settings
        self.jobs = JobService(factory, settings)
        self.audio = audio or AudioService(settings)
        self.transcription = transcription or TranscriptionService(settings)
        self.diarization = diarization or DiarizationService(settings)
        self.extraction = TaskExtractionService(settings, llm or LLMService(settings))

    async def process_meeting(self, job_id: UUID, owner: str):
        async with self.jobs.fenced(job_id, owner) as (_, meeting, job):
            meeting_id, original_path, kind = meeting.id, meeting.original_path, job.kind
        if kind == JobKind.TRANSCRIBE:
            await self._transcribe(job_id, owner, meeting_id, original_path)
        else:
            await self._analyze(job_id, owner, meeting_id)

    async def _transcribe(self, job_id: UUID, owner: str, meeting_id: UUID, original_path: str):
        from pathlib import Path

        # Attempt-specific files fence off a worker that lost its lease during native inference.
        audio_path = (
            meeting_directory(self.settings, meeting_id)
            / "audio"
            / f"{job_id}-{owner}"
            / "meeting.wav"
        )
        await self.jobs.stage(job_id, owner, "AUDIO_EXTRACTION")
        duration = await asyncio.to_thread(self.audio.extract, Path(original_path), audio_path)
        await self.jobs.stage(job_id, owner, "TRANSCRIPTION")
        transcription = await asyncio.to_thread(self.transcription.transcribe, audio_path)
        await self.jobs.stage(job_id, owner, "DIARIZATION")
        turns = (
            await asyncio.to_thread(self.diarization.diarize, audio_path)
            if transcription.segments
            else []
        )
        await self.jobs.stage(job_id, owner, "ALIGNMENT")
        merged = TranscriptMergeService().merge(transcription.segments, turns)
        async with self.jobs.fenced(job_id, owner) as (session, meeting, job):
            await session.execute(
                delete(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id)
            )
            await session.execute(delete(Speaker).where(Speaker.meeting_id == meeting_id))
            session.add_all(
                [
                    Speaker(meeting_id=meeting_id, speaker_id=speaker)
                    for speaker in sorted({segment.speaker_id for segment in merged})
                ]
            )
            session.add_all(
                [
                    TranscriptSegment(meeting_id=meeting_id, ordinal=index, **segment.model_dump())
                    for index, segment in enumerate(merged)
                ]
            )
            meeting.detected_language, meeting.processing_time = (
                transcription.detected_language,
                transcription.processing_time,
            )
            meeting.stt_model, meeting.duration = transcription.model, duration
            self.jobs.succeed(meeting, job, MeetingStatus.AWAITING_MAPPING)

    async def _analyze(self, job_id: UUID, owner: str, meeting_id: UUID):
        await self.jobs.stage(job_id, owner, "LOCAL_LLM_ANALYSIS")
        async with self.factory() as session:
            repository = MeetingRepository(session)
            meeting = await repository.get(meeting_id)
            transcript = await repository.transcript(meeting_id)
            # UUIDs are internal only; the model gets stable segment ordinals and mapped names.
            context = [
                {key: value for key, value in segment.items() if key != "id"}
                for segment in transcript
            ]
            meeting_date, timezone = meeting.meeting_date, meeting.timezone
        analyses = await self.extraction.extract(context, meeting_date, timezone)
        summary, topics, decisions = SummaryService.combine(analyses)
        source = {segment["ordinal"]: segment for segment in transcript}
        async with self.jobs.fenced(job_id, owner) as (session, meeting, job):
            version = meeting.analysis_version + 1
            participants = (
                await session.scalars(
                    select(Participant).where(Participant.meeting_id == meeting_id)
                )
            ).all()
            speakers = (
                await session.scalars(select(Speaker).where(Speaker.meeting_id == meeting_id))
            ).all()
            participant_by_speaker = {s.speaker_id: s.participant_id for s in speakers}
            existing = (
                await session.scalars(select(Task).where(Task.meeting_id == meeting_id))
            ).all()
            by_key = {task.extraction_key: task for task in existing}
            seen = set()
            for analysis in analyses:
                for extracted in analysis.tasks:
                    key = extraction_key(extracted)
                    if key in seen:
                        continue
                    seen.add(key)
                    participant_id = participant_by_speaker.get(extracted.responsible_speaker_id)
                    matches = [
                        p
                        for p in participants
                        if extracted.responsible_name
                        and normalized(p.name) == normalized(extracted.responsible_name)
                    ]
                    if participant_id is None and len(matches) == 1:
                        participant_id = matches[0].id
                    values = {
                        "description": extracted.description,
                        "responsible_participant_id": participant_id,
                        "responsible_name": extracted.responsible_name,
                        "responsible_speaker_id": extracted.responsible_speaker_id,
                        "assigned_by": extracted.assigned_by,
                        "deadline": end_of_day(extracted.deadline, timezone)
                        if extracted.deadline
                        else None,
                        "deadline_raw": extracted.deadline_raw,
                        "priority": Priority(extracted.priority),
                        "confidence": extracted.confidence,
                        "source_transcript_start": min(
                            source[i]["start"] for i in extracted.source_segment_ids
                        ),
                        "source_transcript_end": max(
                            source[i]["end"] for i in extracted.source_segment_ids
                        ),
                        "source_quote": extracted.source_quote,
                        "analysis_version": version,
                    }
                    task = by_key.get(key)
                    if task is None:
                        session.add(Task(meeting_id=meeting_id, extraction_key=key, **values))
                    elif not task.edited_by_user:
                        # Status and completed_at are never reset by re-analysis.
                        for name, value in values.items():
                            setattr(task, name, value)
            # Existing tasks are retained (including absent evidence on a subsequent LLM run).
            # analysis_version exposes older items for human review instead of deleting work.
            from app.services.memory_extraction import persist_memory

            await persist_memory(session, meeting_id, analyses, full=True)
            meeting.memory_analysis_version, meeting.memory_error = version, None
            meeting.summary, meeting.topics, meeting.decisions = summary, topics, decisions
            meeting.analysis_stale, meeting.analysis_version = False, version
            self.jobs.succeed(meeting, job, MeetingStatus.COMPLETED)
