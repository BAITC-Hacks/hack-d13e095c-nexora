import secrets
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, select

from app.api.deps import Config, Session
from app.models import Meeting, Participant, Task
from app.models.conference import AudioChunk, Conference
from app.models.memory import MemoryOccurrence
from app.services.memory_graph import discussion_page, graph, node_id


async def memory_access(
    settings: Config, response: Response, x_memory_key: Annotated[str | None, Header()] = None
):
    expected = settings.memory_access_key or settings.conference_access_key
    if expected and not secrets.compare_digest(x_memory_key or "", expected):
        raise HTTPException(401, "Введите ключ общей карты команды")
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/conferences/memory",
    tags=["corporate-memory"],
    dependencies=[Depends(memory_access)],
)


@router.get("/graph")
async def get_graph(
    session: Session, offset: int = Query(0, ge=0), limit: int = Query(60, ge=1, le=100)
):
    result = await graph(session, offset, limit)
    result["unindexed_meetings"] = await session.scalar(
        select(func.count())
        .select_from(Meeting)
        .where(Meeting.analysis_version > Meeting.memory_analysis_version)
    )
    result["indexing_errors"] = await session.scalar(
        select(func.count())
        .select_from(Meeting)
        .where(
            Meeting.memory_error.is_not(None),
            Meeting.analysis_version > Meeting.memory_analysis_version,
        )
    )
    return result


@router.get("/object")
async def get_object(
    session: Session, id: str = Query(min_length=3, max_length=150), offset: int = Query(0, ge=0)
):
    detail = await discussion_page(session, id, offset)
    if offset == 0:
        context = await graph(session, selected_ids=[UUID(m["id"]) for m in detail["meetings"]])
        edges = [e for e in context["edges"] if e["source"] == id or e["target"] == id]
        ids = {id} | {e["source"] for e in edges} | {e["target"] for e in edges}
        detail["neighborhood"] = {
            "nodes": [n for n in context["nodes"] if n["id"] in ids],
            "edges": edges,
        }
        detail["neighborhood_partial"] = context["next_offset"] is not None
    return detail


@router.get("/search")
async def search(session: Session, q: str = Query(min_length=2, max_length=150)):
    q = q.strip()
    if len(q) < 2:
        return {"nodes": [], "more": False}
    result = {}
    capped = False
    for model, field, kind in (
        (Meeting, Meeting.title, "meeting"),
        (Participant, Participant.name, "person"),
        (Task, Task.description, "task"),
    ):
        records = (
            await session.scalars(
                select(model).where(field.icontains(q, autoescape=True)).limit(61)
            )
        ).all()
        capped = capped or len(records) > 60
        for row in records[:60]:
            label = (
                row.title
                if kind == "meeting"
                else row.name
                if kind == "person"
                else row.description
            )
            result[f"{kind}:{row.id}"] = {
                "id": f"{kind}:{row.id}",
                "kind": kind,
                "label": label,
                "meeting_ids": [str(row.id if kind == "meeting" else row.meeting_id)],
            }
    records = (
        await session.scalars(
            select(MemoryOccurrence)
            .where(MemoryOccurrence.label.icontains(q, autoescape=True))
            .limit(201)
        )
    ).all()
    capped = capped or len(records) > 200
    for row in records[:200]:
        result[node_id(row)] = {
            "id": node_id(row),
            "kind": row.kind,
            "label": row.label,
            "meeting_ids": [str(row.meeting_id)],
        }
    return {"nodes": list(result.values())[:100], "more": capped or len(result) > 100}


@router.get("/protocol/{meeting_id}/{format}")
async def protocol(
    meeting_id: UUID, format: Literal["pdf", "docx"], session: Session, settings: Config
):
    from app.api.exports import export

    room = await session.get(Conference, meeting_id)
    if room:
        incomplete = await session.scalar(
            select(func.count())
            .select_from(AudioChunk)
            .where(
                AudioChunk.conference_id == meeting_id,
                AudioChunk.status.in_(["pending", "processing", "failed"]),
            )
        )
        if (
            room.recording
            or room.analysis_requested
            or room.analysis_status == "analyzing"
            or incomplete
        ):
            raise HTTPException(409, "Дождитесь завершения записи и обработки встречи")
    return await export(meeting_id, format, session, settings)
