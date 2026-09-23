"""One durable live worker: speech and Ollama run concurrently, never cloud inference."""

import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select, update

from app.config import get_settings
from app.db.base import utcnow
from app.db.session import create_database
from app.models import Meeting, Participant, Speaker, Task, TranscriptSegment
from app.models.conference import AudioChunk, Conference
from app.models.enums import MeetingStatus, Priority
from app.repositories.meeting_repository import MeetingRepository
from app.services.llm_service import LLMService
from app.services.speech_client import SpeechClient
from app.services.summary_service import SummaryService
from app.services.task_extraction_service import TaskExtractionService, extraction_key, normalized
from app.utils.dates import aware_utc, end_of_day

logger = logging.getLogger("live-worker")


class LiveProcessor:
    def __init__(self, factory, settings, speech=None, llm=None):
        self.factory, self.settings = factory, settings
        self.speech = speech or SpeechClient(settings)
        self.extraction = TaskExtractionService(settings, llm or LLMService(settings))

    async def speech_once(self):
        async with self.factory() as session:
            stale = utcnow() - timedelta(seconds=self.settings.speech_timeout_seconds + 60)
            await session.execute(
                update(AudioChunk)
                .where(AudioChunk.status == "processing", AudioChunk.claimed_at < stale)
                .values(status="pending")
            )
            chunk = await session.scalar(
                select(AudioChunk)
                .where(AudioChunk.status == "pending")
                .order_by(AudioChunk.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not chunk:
                await session.commit()
                return False
            chunk.status, chunk.claimed_at = "processing", utcnow()
            chunk.attempts += 1
            identity, room_id, path = chunk.id, chunk.conference_id, chunk.path
            await session.commit()
        try:
            result = await self.speech.transcribe(Path(path))
            async with self.factory() as session:
                await session.scalar(
                    select(Conference).where(Conference.id == room_id).with_for_update()
                )
                chunk = await session.get(AudioChunk, identity)
                next_ordinal = await session.scalar(
                    select(func.max(TranscriptSegment.ordinal)).where(
                        TranscriptSegment.meeting_id == room_id
                    )
                )
                ordinal = (next_ordinal + 1) if next_ordinal is not None else 0
                added = 0
                for part in result.segments:
                    start, end = min(part.start, chunk.duration), min(part.end, chunk.duration)
                    if part.text.strip() and end > start:
                        session.add(
                            TranscriptSegment(
                                meeting_id=room_id,
                                ordinal=ordinal,
                                speaker_id=str(chunk.member_id),
                                start=chunk.start + start,
                                end=chunk.start + end,
                                text=part.text.strip(),
                            )
                        )
                        ordinal += 1
                        added += 1
                meeting = await session.get(Meeting, room_id)
                if added:
                    meeting.analysis_stale = True
                meeting.detected_language = result.language
                meeting.stt_model = "self-hosted Whisper"
                meeting.duration = max(meeting.duration or 0, chunk.start + chunk.duration)
                chunk.status, chunk.error = "done", None
                await session.commit()
        except Exception as exc:
            logger.warning("Speech chunk %s failed (%s)", identity, type(exc).__name__)
            async with self.factory() as session:
                chunk = await session.get(AudioChunk, identity)
                chunk.status = "pending" if chunk.attempts < 3 else "failed"
                chunk.error = getattr(exc, "code", "SPEECH_UNAVAILABLE_OR_FAILED")
                await session.commit()
            await asyncio.sleep(2)
        return True

    async def analysis_once(self):
        async with self.factory() as session:
            rooms = (
                await session.scalars(
                    select(Conference).order_by(Conference.analysis_at.asc().nullsfirst())
                )
            ).all()
            selected = None
            for room in rooms:
                if (
                    room.analysis_at
                    and (utcnow() - aware_utc(room.analysis_at)).total_seconds()
                    < self.settings.live_analysis_interval
                ):
                    continue
                latest = await session.scalar(
                    select(func.max(TranscriptSegment.ordinal)).where(
                        TranscriptSegment.meeting_id == room.id
                    )
                )
                full = room.analysis_requested or bool(room.ended_at)
                if latest is None and not room.analysis_requested:
                    continue
                if (
                    latest is not None
                    and latest <= room.analysis_cursor
                    and not room.analysis_requested
                ):
                    continue
                if full:
                    pending = await session.scalar(
                        select(func.count())
                        .select_from(AudioChunk)
                        .where(
                            AudioChunk.conference_id == room.id,
                            AudioChunk.status.in_(["pending", "processing"]),
                        )
                    )
                    stopped = room.recording_stopped_at
                    if pending or (
                        stopped and (utcnow() - aware_utc(stopped)).total_seconds() < 12
                    ):
                        continue
                transcript = await MeetingRepository(session).transcript(room.id)
                context = [
                    {k: v for k, v in s.items() if k != "id"}
                    for s in transcript
                    if full or s["ordinal"] > room.analysis_cursor - 8
                ]
                if not context:
                    room.analysis_requested = False
                    room.analysis_status = "waiting"
                    await session.commit()
                    continue
                meeting = await session.get(Meeting, room.id)
                selected = (room.id, context, meeting.meeting_date, meeting.timezone, full, latest)
                room.analysis_status, room.analysis_error, room.analysis_at = (
                    "analyzing",
                    None,
                    utcnow(),
                )
                # Only consume this request: a later host request remains queued.
                room.analysis_requested = False
                await session.commit()
                break
        if selected is None:
            return False
        room_id, context, meeting_date, timezone, full, latest = selected
        try:
            analyses = await self.extraction.extract(context, meeting_date, timezone)
            summary, topics, decisions = SummaryService.combine(analyses)
            source = {s["ordinal"]: s for s in context}
            async with self.factory() as session:
                room = await session.scalar(
                    select(Conference).where(Conference.id == room_id).with_for_update()
                )
                meeting = await session.scalar(
                    select(Meeting).where(Meeting.id == room_id).with_for_update()
                )
                participants = (
                    await session.scalars(
                        select(Participant).where(Participant.meeting_id == room_id)
                    )
                ).all()
                speakers = (
                    await session.scalars(select(Speaker).where(Speaker.meeting_id == room_id))
                ).all()
                mapping = {s.speaker_id: s.participant_id for s in speakers}
                existing = (
                    await session.scalars(select(Task).where(Task.meeting_id == room_id))
                ).all()
                by_key = {t.extraction_key: t for t in existing}
                version = meeting.analysis_version + 1
                for analysis in analyses:
                    for item in analysis.tasks:
                        key = extraction_key(item)
                        person_id = mapping.get(item.responsible_speaker_id)
                        matches = [
                            p
                            for p in participants
                            if item.responsible_name
                            and normalized(p.name) == normalized(item.responsible_name)
                        ]
                        if person_id is None and len(matches) == 1:
                            person_id = matches[0].id
                        values = dict(
                            description=item.description,
                            responsible_participant_id=person_id,
                            responsible_name=item.responsible_name,
                            responsible_speaker_id=item.responsible_speaker_id,
                            assigned_by=item.assigned_by,
                            deadline=end_of_day(item.deadline, timezone) if item.deadline else None,
                            deadline_raw=item.deadline_raw,
                            priority=Priority(item.priority),
                            confidence=item.confidence,
                            source_transcript_start=min(
                                source[i]["start"] for i in item.source_segment_ids
                            ),
                            source_transcript_end=max(
                                source[i]["end"] for i in item.source_segment_ids
                            ),
                            source_quote=item.source_quote,
                            analysis_version=version,
                        )
                        task = by_key.get(key)
                        # An overlapping analysis window may phrase the same evidence differently.
                        if task is None:
                            task = next(
                                (
                                    t
                                    for t in existing
                                    if normalized(t.source_quote) == normalized(item.source_quote)
                                    and normalized(t.description) == normalized(item.description)
                                ),
                                None,
                            )
                        if task is None:
                            task = Task(meeting_id=room_id, extraction_key=key, **values)
                            session.add(task)
                            existing.append(task)
                            by_key[key] = task
                        elif not task.edited_by_user:
                            for name, value in values.items():
                                setattr(task, name, value)
                meeting.summary = (
                    summary
                    if full
                    else "\n\n".join(dict.fromkeys(filter(None, [meeting.summary, summary])))
                )
                meeting.topics = topics if full else list(dict.fromkeys(meeting.topics + topics))
                meeting.decisions = (
                    decisions if full else list(dict.fromkeys(meeting.decisions + decisions))
                )
                meeting.analysis_version = version
                if room.ended_at and room.baseline_tasks is not None:
                    from app.services.briefing_service import freeze_tasks

                    await session.flush()
                    await freeze_tasks(session, room)
                actual_latest = await session.scalar(
                    select(func.max(TranscriptSegment.ordinal)).where(
                        TranscriptSegment.meeting_id == room_id
                    )
                )
                meeting.analysis_stale = actual_latest != latest
                meeting.status = (
                    MeetingStatus.COMPLETED if room.ended_at else MeetingStatus.PROCESSING
                )
                room.analysis_cursor, room.analysis_status, room.analysis_error = (
                    latest,
                    "ready",
                    None,
                )
                await session.commit()
        except Exception as exc:
            logger.warning("Room %s analysis failed (%s)", room_id, type(exc).__name__)
            async with self.factory() as session:
                room = await session.get(Conference, room_id)
                room.analysis_status = "error"
                room.analysis_error = getattr(exc, "code", "OLLAMA_ANALYSIS_FAILED")
                if full:
                    room.analysis_requested = True
                await session.commit()
        return True


async def main():
    settings = get_settings()
    engine, factory = create_database(settings)
    processor = LiveProcessor(factory, settings)
    from app.services.briefing_service import BriefingProcessor

    briefings = BriefingProcessor(factory, settings)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)

    async def loop(operation, interval):
        while True:
            try:
                await operation()
            except Exception as exc:
                logger.error("Live worker iteration failed (%s)", type(exc).__name__)
            await asyncio.sleep(interval)

    async def heartbeat():
        path = settings.storage_dir / "live-worker.heartbeat"
        await asyncio.to_thread(path.write_text, utcnow().isoformat())

    try:
        await asyncio.gather(
            loop(processor.speech_once, 0.3),
            loop(processor.analysis_once, 3),
            loop(briefings.once, 1),
            loop(heartbeat, 5),
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
