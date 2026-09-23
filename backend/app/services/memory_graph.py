"""Relational graph projection. Edges carry provenance, not guessed causality."""

from collections import defaultdict
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import Meeting, Participant, Speaker, Task, TranscriptSegment
from app.models.briefing import ConferenceBriefing
from app.models.memory import MemoryOccurrence
from app.repositories.task_repository import effective_status
from app.services.memory_extraction import digest
from app.services.task_extraction_service import normalized
from app.utils.dates import aware_utc


def node_id(row):
    return f"decision:{row.id}" if row.kind == "decision" else f"{row.kind}:{row.object_key}"


def iso(value):
    return aware_utc(value).isoformat() if value else None


async def graph(session, offset=0, limit=60, selected_ids=None):
    query = select(Meeting)
    if selected_ids is not None:
        query = query.where(Meeting.id.in_(selected_ids))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    meetings = (
        await session.scalars(
            query.order_by(Meeting.meeting_date.desc(), Meeting.id).offset(offset).limit(limit)
        )
    ).all()
    ids = [m.id for m in meetings]
    nodes, edges = {}, {}

    def node(key, kind, label, meeting_id, **meta):
        if key not in nodes:
            nodes[key] = {"id": key, "kind": kind, "label": label, "meeting_ids": [], **meta}
        if str(meeting_id) not in nodes[key]["meeting_ids"]:
            nodes[key]["meeting_ids"].append(str(meeting_id))
        return key

    def edge(source, target, relation, label, meeting_id):
        if source == target or source not in nodes or target not in nodes:
            return
        key = digest(f"{source}:{target}:{relation}")
        if key not in edges:
            edges[key] = {
                "id": key,
                "source": source,
                "target": target,
                "relation": relation,
                "label": label,
                "meeting_ids": [],
            }
        if str(meeting_id) not in edges[key]["meeting_ids"]:
            edges[key]["meeting_ids"].append(str(meeting_id))

    for meeting in meetings:
        node(
            f"meeting:{meeting.id}",
            "meeting",
            meeting.title,
            meeting.id,
            date=iso(meeting.meeting_date),
        )
        if meeting.analysis_version:
            document = node(
                f"protocol:{meeting.id}",
                "document",
                f"Протокол: {meeting.title}",
                meeting.id,
                protocol=True,
                stale=meeting.analysis_stale,
            )
            edge(f"meeting:{meeting.id}", document, "protocol", "Итоговый протокол", meeting.id)
    if not ids:
        return {"nodes": [], "edges": [], "total_meetings": total, "next_offset": None}
    participants = (
        await session.scalars(select(Participant).where(Participant.meeting_id.in_(ids)))
    ).all()
    speakers = (await session.scalars(select(Speaker).where(Speaker.meeting_id.in_(ids)))).all()
    speaker_people = {(s.meeting_id, s.speaker_id): s.participant_id for s in speakers}
    for person in participants:
        key = node(
            f"person:{person.id}",
            "person",
            person.name,
            person.meeting_id,
            identity_note="Профиль участника этой встречи. Одинаковое имя не подтверждает личность.",
        )
        edge(key, f"meeting:{person.meeting_id}", "attended", "Участвовал", person.meeting_id)
    tasks = (await session.scalars(select(Task).where(Task.meeting_id.in_(ids)))).all()
    for task in tasks:
        key = node(
            f"task:{task.id}",
            "task",
            task.description,
            task.meeting_id,
            status=effective_status(task).value,
            responsible=task.responsible_name,
        )
        edge(
            key,
            f"meeting:{task.meeting_id}",
            "assigned_in",
            "Поставлена на встрече",
            task.meeting_id,
        )
        if task.responsible_participant_id:
            edge(
                f"person:{task.responsible_participant_id}",
                key,
                "responsible",
                "Ответственный",
                task.meeting_id,
            )
        if task.deadline:
            deadline = node(
                f"deadline:{task.id}",
                "deadline",
                iso(task.deadline),
                task.meeting_id,
                date=iso(task.deadline),
                status=effective_status(task).value,
            )
            edge(key, deadline, "due", "Срок исполнения", task.meeting_id)
        edge(key, f"protocol:{task.meeting_id}", "documented", "В протоколе", task.meeting_id)
    occurrences = (
        await session.scalars(select(MemoryOccurrence).where(MemoryOccurrence.meeting_id.in_(ids)))
    ).all()
    by_meeting = defaultdict(list)
    supported_decisions = defaultdict(set)
    for occurrence in occurrences:
        key = node_id(occurrence)
        node(key, occurrence.kind, occurrence.label, occurrence.meeting_id)
        edge(
            key,
            f"meeting:{occurrence.meeting_id}",
            "mentioned",
            "Обсуждалось",
            occurrence.meeting_id,
        )
        if occurrence.kind == "decision":
            supported_decisions[occurrence.meeting_id].add(normalized(occurrence.label))
            edge(
                key,
                f"protocol:{occurrence.meeting_id}",
                "documented",
                "В протоколе",
                occurrence.meeting_id,
            )
        by_meeting[occurrence.meeting_id].append(occurrence)
    # Preserve older decisions, visibly without retroactively invented quotes.
    for meeting in meetings:
        for decision in meeting.decisions or []:
            if normalized(decision) not in supported_decisions[meeting.id]:
                key = node(
                    f"legacy-decision:{meeting.id}:{digest(decision)}",
                    "decision",
                    decision,
                    meeting.id,
                    legacy=True,
                )
                edge(
                    key,
                    f"meeting:{meeting.id}",
                    "recorded",
                    "В итогах встречи; цитата не сохранена",
                    meeting.id,
                )
    segments = (
        await session.scalars(
            select(TranscriptSegment).where(TranscriptSegment.meeting_id.in_(ids))
        )
    ).all()
    by_ordinal = {(s.meeting_id, s.ordinal): s for s in segments}
    for meeting_id, mentions in by_meeting.items():
        # Co-occurrence is explicitly labelled; it never asserts ownership/dependency.
        for index, a in enumerate(mentions):
            for b in mentions[index + 1 :]:
                if set(a.segment_ids) & set(b.segment_ids):
                    edge(
                        node_id(a),
                        node_id(b),
                        "same_discussion",
                        "Обсуждались в одной реплике",
                        meeting_id,
                    )
            for ordinal in a.segment_ids:
                segment = by_ordinal.get((meeting_id, ordinal))
                if segment:
                    person_id = speaker_people.get((meeting_id, segment.speaker_id))
                    if person_id:
                        edge(
                            f"person:{person_id}",
                            node_id(a),
                            "discussed",
                            "Упоминал в обсуждении",
                            meeting_id,
                        )
            for task in tasks:
                if task.meeting_id != meeting_id:
                    continue
                overlap = any(
                    (s := by_ordinal.get((meeting_id, ordinal))) is not None
                    and task.source_transcript_start is not None
                    and task.source_transcript_end is not None
                    and s.start < task.source_transcript_end
                    and s.end > task.source_transcript_start
                    for ordinal in a.segment_ids
                )
                if overlap:
                    edge(
                        f"task:{task.id}",
                        node_id(a),
                        "same_discussion",
                        "Обсуждались в одной реплике",
                        meeting_id,
                    )
    followups = (
        await session.scalars(
            select(ConferenceBriefing).where(
                ConferenceBriefing.previous_id.is_not(None),
                (ConferenceBriefing.id.in_(ids)) | (ConferenceBriefing.previous_id.in_(ids)),
            )
        )
    ).all()
    # Include boundary meeting nodes so pagination does not sever explicit follow-up edges.
    extra_ids = {b.id for b in followups} | {b.previous_id for b in followups}
    for meeting in (await session.scalars(select(Meeting).where(Meeting.id.in_(extra_ids)))).all():
        node(
            f"meeting:{meeting.id}",
            "meeting",
            meeting.title,
            meeting.id,
            date=iso(meeting.meeting_date),
        )
    for b in followups:
        edge(
            f"meeting:{b.previous_id}", f"meeting:{b.id}", "next_meeting", "Следующая встреча", b.id
        )
        edge(
            f"protocol:{b.previous_id}",
            f"meeting:{b.id}",
            "previous_material",
            "Материалы прошлого созвона",
            b.id,
        )
    return {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "total_meetings": total,
        "next_offset": offset + limit if offset + limit < total else None,
    }


async def object_info(session, identity):
    """Resolve any object independently of the currently visible graph page."""
    kind, _, value = identity.partition(":")
    meeting_ids, occurrences, task, person, meeting = [], [], None, None, None
    try:
        if kind in {"project", "document"}:
            occurrences = (
                await session.scalars(
                    select(MemoryOccurrence).where(
                        MemoryOccurrence.kind == kind, MemoryOccurrence.object_key == value
                    )
                )
            ).all()
            if not occurrences:
                raise HTTPException(404, "Объект не найден")
            label = occurrences[0].label
            meeting_ids = [o.meeting_id for o in occurrences]
        elif kind == "decision":
            occurrence = await session.get(MemoryOccurrence, UUID(value))
            if not occurrence or occurrence.kind != "decision":
                raise HTTPException(404, "Решение не найдено")
            occurrences, label, meeting_ids = (
                [occurrence],
                occurrence.label,
                [occurrence.meeting_id],
            )
        elif kind == "legacy-decision":
            room, _, key = value.partition(":")
            meeting = await session.get(Meeting, UUID(room))
            label = (
                next((s for s in (meeting.decisions or []) if digest(s) == key), None)
                if meeting
                else None
            )
            if not label:
                raise HTTPException(404, "Решение не найдено")
            meeting_ids = [meeting.id]
        elif kind in {"task", "deadline"}:
            task = await session.get(Task, UUID(value))
            if not task or (kind == "deadline" and not task.deadline):
                raise HTTPException(404, "Поручение не найдено")
            label = task.description if kind == "task" else iso(task.deadline)
            meeting_ids = [task.meeting_id]
        elif kind == "person":
            person = await session.get(Participant, UUID(value))
            if not person:
                raise HTTPException(404, "Участник не найден")
            label, meeting_ids = person.name, [person.meeting_id]
        elif kind in {"meeting", "protocol"}:
            meeting = await session.get(Meeting, UUID(value))
            if not meeting or (kind == "protocol" and not meeting.analysis_version):
                raise HTTPException(404, "Встреча или протокол не найдены")
            label, meeting_ids = meeting.title, [meeting.id]
        else:
            raise HTTPException(404, "Объект не найден")
    except ValueError:
        raise HTTPException(404, "Объект не найден") from None
    meetings = (
        await session.scalars(
            select(Meeting)
            .where(Meeting.id.in_(set(meeting_ids)))
            .order_by(Meeting.meeting_date.desc())
        )
    ).all()
    same_names = []
    if person:
        # Suggestions are not identity merges: keep exact meeting-specific profiles.
        candidates = (
            await session.scalars(select(Participant).where(Participant.id != person.id))
        ).all()
        same_names = [
            {"id": f"person:{p.id}", "label": p.name, "meeting_id": str(p.meeting_id)}
            for p in candidates
            if normalized(p.name) == normalized(person.name)
        ]
    return {
        "id": identity,
        "kind": "document"
        if kind == "protocol"
        else "decision"
        if kind == "legacy-decision"
        else kind,
        "label": label,
        "meeting_ids": list(set(meeting_ids)),
        "occurrences": occurrences,
        "task": task,
        "person": person,
        "meetings": [
            {"id": str(m.id), "title": m.title, "date": iso(m.meeting_date)} for m in meetings
        ],
        "same_names": same_names,
        "protocol": kind == "protocol",
        "legacy": kind == "legacy-decision",
    }


async def discussion_page(session, identity, offset=0, limit=50):
    info = await object_info(session, identity)
    rows = []
    if info["occurrences"]:
        for occurrence in info["occurrences"]:
            segments = (
                await session.scalars(
                    select(TranscriptSegment)
                    .where(
                        TranscriptSegment.meeting_id == occurrence.meeting_id,
                        TranscriptSegment.ordinal.in_(occurrence.segment_ids),
                    )
                    .order_by(TranscriptSegment.ordinal)
                )
            ).all()
            rows.append(
                {
                    "id": str(occurrence.id),
                    "meeting_id": str(occurrence.meeting_id),
                    "quote": occurrence.quote,
                    "start": min((s.start for s in segments), default=None),
                    "active": occurrence.active,
                    "source_matches": normalized(occurrence.quote)
                    in normalized(" ".join(s.text for s in segments)),
                    "url": occurrence.url,
                    "label": occurrence.label,
                    "source": "ИИ · проверенная цитата",
                }
            )
    elif info["task"]:
        task = info["task"]
        rows.append(
            {
                "id": str(task.id),
                "meeting_id": str(task.meeting_id),
                "quote": task.source_quote,
                "start": task.source_transcript_start,
                "active": True,
                "source": "Основание поручения",
            }
        )
    else:
        query = (
            select(TranscriptSegment, Participant.name)
            .outerjoin(
                Speaker,
                (Speaker.meeting_id == TranscriptSegment.meeting_id)
                & (Speaker.speaker_id == TranscriptSegment.speaker_id),
            )
            .outerjoin(Participant, Participant.id == Speaker.participant_id)
        )
        if info["person"]:
            query = query.where(Speaker.participant_id == info["person"].id)
        else:
            query = query.where(TranscriptSegment.meeting_id.in_(info["meeting_ids"]))
        query = query.order_by(
            TranscriptSegment.meeting_id, TranscriptSegment.start, TranscriptSegment.ordinal
        )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        page = (await session.execute(query.offset(offset).limit(limit))).all()
        rows = [
            {
                "id": str(s.id),
                "meeting_id": str(s.meeting_id),
                "quote": s.text,
                "start": s.start,
                "active": True,
                "source": name or "Участник не указан",
            }
            for s, name in page
        ]
        return detail_response(info, rows, total, offset, limit)
    rows.sort(key=lambda row: (row["meeting_id"], row.get("start") or 0, row["id"]))
    return detail_response(info, rows[offset : offset + limit], len(rows), offset, limit)


def detail_response(info, rows, total, offset, limit):
    task = info["task"]
    return {
        "id": info["id"],
        "kind": info["kind"],
        "label": info["label"],
        "meetings": info["meetings"],
        "same_names": info["same_names"],
        "protocol": info["protocol"],
        "legacy": info["legacy"],
        "task": {
            "id": str(task.id),
            "status": effective_status(task).value,
            "responsible": task.responsible_name,
            "deadline": iso(task.deadline),
        }
        if task
        else None,
        "discussions": rows,
        "total": total,
        "next_offset": offset + limit if offset + limit < total else None,
    }
