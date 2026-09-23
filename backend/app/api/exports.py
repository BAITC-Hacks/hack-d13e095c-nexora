import asyncio
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import aiofiles
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import Config, Session
from app.models import Participant, Task
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.task_repository import effective_status
from app.services.export_service import ExportService
from app.utils.dates import aware_utc
from app.utils.errors import PipelineError
from app.utils.files import meeting_directory

router = APIRouter(prefix="/meetings/{meeting_id}/exports", tags=["exports"])


@router.get("/{format}")
async def export(
    meeting_id: UUID, format: Literal["docx", "pdf"], session: Session, settings: Config
):
    repository = MeetingRepository(session)
    meeting = await repository.editable(meeting_id)
    if meeting.analysis_version == 0 or meeting.analysis_stale:
        raise HTTPException(409, "Run analysis with the current speaker mapping before exporting")
    participants = (
        await session.scalars(
            select(Participant)
            .where(Participant.meeting_id == meeting_id)
            .order_by(Participant.created_at)
        )
    ).all()
    tasks = (
        await session.scalars(
            select(Task)
            .where(Task.meeting_id == meeting_id)
            .order_by(Task.source_transcript_start, Task.created_at)
        )
    ).all()
    snapshot = {
        "title": meeting.title,
        "meeting_date": aware_utc(meeting.meeting_date)
        .astimezone(ZoneInfo(meeting.timezone))
        .isoformat(),
        "timezone": meeting.timezone,
        "summary": meeting.summary or "",
        "topics": meeting.topics,
        "decisions": meeting.decisions,
        "analysis_version": meeting.analysis_version,
        "participants": [{"name": p.name, "position": p.position} for p in participants],
        "transcript": await repository.transcript(meeting_id),
        "tasks": [
            {
                "description": task.description,
                "responsible_name": task.responsible_name,
                "assigned_by": task.assigned_by,
                "deadline": aware_utc(task.deadline)
                .astimezone(ZoneInfo(meeting.timezone))
                .isoformat()
                if task.deadline
                else None,
                "status": effective_status(task).value,
                "priority": task.priority.value,
                "confidence": task.confidence,
                "source_quote": task.source_quote,
                "analysis_version": task.analysis_version,
            }
            for task in tasks
        ],
    }
    await session.commit()
    service = ExportService(settings)
    try:
        content = await asyncio.to_thread(
            service.docx if format == "docx" else service.pdf, snapshot
        )
    except PipelineError as exc:
        raise HTTPException(503, exc.code) from exc
    directory = meeting_directory(settings, meeting_id) / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"protocol-{uuid4()}.{format}"
    async with aiofiles.open(path, "xb") as output:
        await output.write(content)
    media = (
        "application/pdf"
        if format == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(
        path,
        media_type=media,
        filename=f"meeting-{meeting_id}.{format}",
        headers={"Cache-Control": "no-store"},
    )
