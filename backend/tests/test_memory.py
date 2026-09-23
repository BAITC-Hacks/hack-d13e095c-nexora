from datetime import UTC, datetime

from sqlalchemy import select

from app.models import Meeting, Participant, Speaker, Task, TranscriptSegment
from app.models.memory import MemoryOccurrence
from app.schemas.analysis import MeetingAnalysis, MemoryObject, SupportedDecision
from app.services.memory_extraction import MemoryBackfill, digest, persist_memory
from app.services.task_extraction_service import TaskExtractionService

NOW = datetime(2026, 9, 23, tzinfo=UTC)
QUOTE = "По проекту Атлас подготовлю документ План запуска до пятницы."


def analysis():
    return MeetingAnalysis(
        summary="Обсуждение запуска",
        topics=[],
        tasks=[],
        decisions=[
            SupportedDecision(
                description="Подготовить план", source_quote=QUOTE, source_segment_ids=[0]
            )
        ],
        memory_objects=[
            MemoryObject(kind="project", name="Атлас", source_quote=QUOTE, source_segment_ids=[0]),
            MemoryObject(
                kind="document", name="План запуска", source_quote=QUOTE, source_segment_ids=[0]
            ),
        ],
    )


async def seed(env, title="Запуск Атласа"):
    async with env["factory"]() as session:
        meeting = Meeting(
            title=title,
            meeting_date=NOW,
            timezone="Asia/Almaty",
            original_path="",
            original_filename="live",
            mime_type="audio/webm",
            file_size=0,
            analysis_version=1,
            analysis_stale=False,
        )
        session.add(meeting)
        await session.flush()
        person = Participant(meeting_id=meeting.id, name="Алия")
        session.add(person)
        await session.flush()
        session.add(Speaker(meeting_id=meeting.id, speaker_id="s0", participant_id=person.id))
        session.add(
            TranscriptSegment(
                meeting_id=meeting.id, ordinal=0, speaker_id="s0", start=0, end=8, text=QUOTE
            )
        )
        task = Task(
            meeting_id=meeting.id,
            description="Подготовить план",
            responsible_participant_id=person.id,
            responsible_name=person.name,
            deadline=NOW,
            confidence=1,
            source_quote=QUOTE,
            source_transcript_start=0,
            source_transcript_end=8,
            extraction_key="plan",
            analysis_version=1,
        )
        session.add(task)
        await persist_memory(session, meeting.id, [analysis()])
        await session.commit()
        return meeting.id, person.id, task.id


async def test_graph_shared_objects_evidence_and_identity(env):
    m1, p1, t1 = await seed(env)
    m2, p2, _ = await seed(env, "Продолжение")
    client = env["client"]
    response = await client.get("/api/v1/conferences/memory/graph")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert {n["kind"] for n in data["nodes"]} == {
        "meeting",
        "person",
        "task",
        "deadline",
        "decision",
        "project",
        "document",
    }
    assert len([n for n in data["nodes"] if n["kind"] == "person"]) == 2
    projects = [n for n in data["nodes"] if n["kind"] == "project"]
    assert len(projects) == 1 and set(projects[0]["meeting_ids"]) == {str(m1), str(m2)}
    assert any(
        e["source"] == f"person:{p1}"
        and e["target"] == f"task:{t1}"
        and e["relation"] == "responsible"
        for e in data["edges"]
    )
    assert any(e["relation"] == "same_discussion" for e in data["edges"])
    detail = (
        await client.get("/api/v1/conferences/memory/object", params={"id": projects[0]["id"]})
    ).json()
    assert detail["total"] == 2 and len(detail["meetings"]) == 2
    assert all(
        d["quote"] == QUOTE and d["source_matches"] and d["start"] == 0
        for d in detail["discussions"]
    )
    person = (
        await client.get("/api/v1/conferences/memory/object", params={"id": f"person:{p1}"})
    ).json()
    assert person["same_names"][0]["id"] == f"person:{p2}"
    assert person["total"] == 1
    assert "token" not in response.text and "invite" not in response.text
    assert (
        await client.get("/api/v1/conferences/memory/object", params={"id": "task:invalid"})
    ).status_code == 404


async def test_index_is_idempotent_and_archives_evidence(env):
    m, _, _ = await seed(env)
    async with env["factory"]() as session:
        await persist_memory(session, m, [analysis()])
        rows = (await session.scalars(select(MemoryOccurrence))).all()
        assert len(rows) == 3
        await persist_memory(session, m, [])
        assert all(not r.active for r in rows)
        await session.commit()
    detail = (
        await env["client"].get(
            "/api/v1/conferences/memory/object", params={"id": f"project:{digest('Атлас')}"}
        )
    ).json()
    assert detail["total"] == 1 and not detail["discussions"][0]["active"]


async def test_team_key_protects_all_memory_endpoints(env):
    m, _, _ = await seed(env)
    env["settings"].memory_access_key = "team-secret"
    for path in ["/graph", "/search?q=Атлас", f"/object?id=meeting:{m}", f"/protocol/{m}/pdf"]:
        assert (await env["client"].get("/api/v1/conferences/memory" + path)).status_code == 401
    assert (
        await env["client"].get(
            "/api/v1/conferences/memory/graph", headers={"X-Memory-Key": "team-secret"}
        )
    ).status_code == 200
    env["settings"].memory_access_key = None
    env["settings"].conference_access_key = "fallback"
    assert (await env["client"].get("/api/v1/conferences/memory/graph")).status_code == 401
    assert (
        await env["client"].get(
            "/api/v1/conferences/memory/graph", headers={"X-Memory-Key": "fallback"}
        )
    ).status_code == 200


async def test_search_global_and_literal(env):
    await seed(env)
    client = env["client"]
    nodes = (await client.get("/api/v1/conferences/memory/search", params={"q": "Атлас"})).json()[
        "nodes"
    ]
    assert any(n["kind"] == "project" for n in nodes)
    assert (await client.get("/api/v1/conferences/memory/search", params={"q": "%%"})).json()[
        "nodes"
    ] == []


async def test_memory_evidence_and_urls(env):
    service = TaskExtractionService(env["settings"], None)
    result = analysis()
    result.memory_objects += [
        MemoryObject(kind="project", name="Выдуманный", source_quote=QUOTE, source_segment_ids=[0]),
        MemoryObject(kind="project", name="Атлас", source_quote=QUOTE, source_segment_ids=[99]),
        MemoryObject(
            kind="document",
            name="План запуска",
            source_quote="План запуска готов",
            source_segment_ids=[0],
        ),
    ]
    result.memory_objects[1].url = "javascript:alert(1)"
    validated = service.validate_evidence(
        result,
        [{"ordinal": 0, "text": QUOTE, "speaker_id": "s0", "speaker_name": "Алия"}],
        NOW,
        "UTC",
    )
    assert len(validated.memory_objects) == 2
    assert validated.memory_objects[1].url is None


async def test_backfill_preserves_tasks_and_indexes_old_analysis(env):
    m, _, t = await seed(env)

    class Extraction:
        async def extract(self, transcript, date, zone):
            assert transcript[0]["ordinal"] == 0
            return [analysis()]

    worker = MemoryBackfill(env["factory"], env["settings"], Extraction())
    assert await worker.once()
    assert not await worker.once()
    async with env["factory"]() as session:
        assert (await session.get(Meeting, m)).memory_analysis_version == 1
        assert (await session.get(Task, t)).description == "Подготовить план"


async def test_backfill_error_is_retryable_and_does_not_claim_success(env):
    m, _, _ = await seed(env)

    class Extraction:
        async def extract(self, *args):
            raise RuntimeError("offline")

    worker = MemoryBackfill(env["factory"], env["settings"], Extraction())
    assert await worker.once()
    assert not await worker.once()
    async with env["factory"]() as session:
        row = await session.get(Meeting, m)
        assert row.memory_error == "MEMORY_INDEXING_FAILED" and row.memory_analysis_version == 0


async def test_backfill_discards_outdated_result(env):
    m, _, _ = await seed(env)

    class Extraction:
        async def extract(self, *args):
            async with env["factory"]() as session:
                row = await session.get(Meeting, m)
                row.analysis_version = 2
                await session.commit()
            return [analysis()]

    await MemoryBackfill(env["factory"], env["settings"], Extraction()).once()
    async with env["factory"]() as session:
        assert (await session.get(Meeting, m)).memory_analysis_version == 0
