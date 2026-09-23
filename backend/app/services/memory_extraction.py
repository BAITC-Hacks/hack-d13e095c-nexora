import hashlib

from sqlalchemy import select

from app.models.memory import MemoryOccurrence
from app.services.task_extraction_service import normalized


def digest(value):
    return hashlib.sha256(normalized(value).encode()).hexdigest()


async def persist_memory(session, meeting_id, analyses, full=True):
    """Called only after TaskExtractionService validates IDs and literal quotes."""
    rows = (
        await session.scalars(
            select(MemoryOccurrence).where(MemoryOccurrence.meeting_id == meeting_id)
        )
    ).all()
    existing = {(r.kind, r.object_key, r.evidence_key): r for r in rows}
    if full:
        for row in rows:
            row.active = False
    for analysis in analyses:
        objects = [
            (o.kind, o.name, o.source_quote, o.source_segment_ids, o.url)
            for o in analysis.memory_objects
        ]
        objects += [
            ("decision", d.description, d.source_quote, d.source_segment_ids, None)
            for d in analysis.decisions
        ]
        for kind, label, quote, segments, url in objects:
            key, evidence = digest(label), digest(quote)
            identity = (kind, key, evidence)
            row = existing.get(identity)
            if not row:
                row = MemoryOccurrence(
                    meeting_id=meeting_id,
                    kind=kind,
                    label=label,
                    object_key=key,
                    evidence_key=evidence,
                    quote=quote,
                    segment_ids=segments,
                    url=url,
                )
                session.add(row)
                existing[identity] = row
            else:
                row.quote, row.segment_ids, row.url = quote, segments, url
            row.active = True
    await session.flush()


class MemoryBackfill:
    """Bounded, retryable indexing for meetings analyzed before this feature existed."""

    def __init__(self, factory, settings, extraction=None):
        from app.services.llm_service import LLMService
        from app.services.task_extraction_service import TaskExtractionService

        self.factory = factory
        self.extraction = extraction or TaskExtractionService(settings, LLMService(settings))

    async def once(self):
        import asyncio
        from datetime import timedelta

        from app.db.base import utcnow
        from app.models import Meeting
        from app.repositories.meeting_repository import MeetingRepository

        async with self.factory() as session:
            meeting = await session.scalar(
                select(Meeting)
                .where(
                    Meeting.analysis_version > Meeting.memory_analysis_version,
                    Meeting.analysis_stale.is_(False),
                    (Meeting.memory_attempted_at.is_(None))
                    | (Meeting.memory_attempted_at < utcnow() - timedelta(minutes=5)),
                )
                .order_by(Meeting.memory_attempted_at.asc().nullsfirst())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not meeting:
                return False
            meeting.memory_attempted_at = utcnow()
            identity, version, date, timezone = (
                meeting.id,
                meeting.analysis_version,
                meeting.meeting_date,
                meeting.timezone,
            )
            transcript = await MeetingRepository(session).transcript(identity)
            context = [{k: v for k, v in s.items() if k != "id"} for s in transcript]
            await session.commit()
        try:
            async with asyncio.timeout(120):
                analyses = await self.extraction.extract(context, date, timezone) if context else []
            async with self.factory() as session:
                meeting = await session.scalar(
                    select(Meeting).where(Meeting.id == identity).with_for_update()
                )
                if meeting and meeting.analysis_version == version and not meeting.analysis_stale:
                    await persist_memory(session, identity, analyses, full=True)
                    meeting.memory_analysis_version, meeting.memory_error = version, None
                await session.commit()
        except Exception as exc:
            async with self.factory() as session:
                meeting = await session.get(Meeting, identity)
                if meeting:
                    meeting.memory_error = getattr(exc, "code", "MEMORY_INDEXING_FAILED")
                    await session.commit()
        return True
