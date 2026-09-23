from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

import pytest
from docx import Document
from pypdf import PdfReader
from sqlalchemy import select

from app.models import Job, Task
from app.models.enums import JobStatus
from app.services.job_service import JobService
from app.utils.dates import aware_utc
from app.utils.errors import LeaseLost, PipelineError
from tests.helpers import (
    PREFIX,
    analyzed_meeting,
    fake_processor,
    prepared_meeting,
    run_next,
    upload,
)


async def test_complete_workflow_and_manual_edits_survive_reanalysis(env):
    client = env["client"]
    mid, processor, people = await analyzed_meeting(env)
    meeting = (await client.get(f"{PREFIX}/meetings/{mid}")).json()
    assert meeting["status"] == "COMPLETED", meeting
    assert meeting["detected_language"] == "ru"
    assert meeting["stt_model"] == "large-v3"
    transcript = (await client.get(f"{PREFIX}/meetings/{mid}/transcript")).json()
    assert [item["speaker_name"] for item in transcript] == ["Ерлан", "Айдар"]
    task = (await client.get(f"{PREFIX}/tasks", params={"meeting_id": mid})).json()[0]
    assert task["responsible_participant_id"] == people[1]
    assert task["deadline"].startswith("2026-09-25T18:59:59")  # End of Friday in UTC+5.
    assert processor.extraction.llm.contexts[0]["MEETING_LOCAL_DATE"].startswith("2026-09-23")
    response = await client.patch(
        f"{PREFIX}/tasks/{task['id']}",
        json={"status": "COMPLETED", "description": "Подготовить итоговый отчёт"},
    )
    assert response.status_code == 200, response.text
    completed_at = response.json()["completed_at"]
    assert completed_at
    await client.post(f"{PREFIX}/meetings/{mid}/analyze", json={})
    await run_next(env, processor)
    tasks = (await client.get(f"{PREFIX}/tasks", params={"meeting_id": mid})).json()
    assert len(tasks) == 1
    assert tasks[0]["description"] == "Подготовить итоговый отчёт"
    assert tasks[0]["status"] == "COMPLETED"
    assert aware_utc(datetime.fromisoformat(tasks[0]["completed_at"])) == aware_utc(
        datetime.fromisoformat(completed_at)
    )
    assert processor.transcription.transcribe.call_count == 1
    assert processor.diarization.diarize.call_count == 1


async def test_mapping_gate_unmapped_override_and_duplicate_queue(env):
    client = env["client"]
    mid = (await upload(env)).json()["id"]
    assert (await client.post(f"{PREFIX}/meetings/{mid}/process")).status_code == 409
    processor = fake_processor(env)
    await run_next(env, processor)
    assert (await client.post(f"{PREFIX}/meetings/{mid}/analyze", json={})).status_code == 409
    assert (
        await client.post(f"{PREFIX}/meetings/{mid}/analyze", json={"allow_unmapped": True})
    ).status_code == 202
    assert (
        await client.post(f"{PREFIX}/meetings/{mid}/analyze", json={"allow_unmapped": True})
    ).status_code == 409
    await run_next(env, processor)
    assert (await client.get(f"{PREFIX}/meetings/{mid}")).json()["status"] == "COMPLETED"


async def test_cross_meeting_mapping_and_assignment_rejected(env):
    client = env["client"]
    mid, _, _ = await analyzed_meeting(env)
    other = (await upload(env)).json()["id"]
    person = (
        await client.post(f"{PREFIX}/meetings/{other}/participants", json={"name": "Чужой"})
    ).json()["id"]
    response = await client.patch(
        f"{PREFIX}/meetings/{mid}/speakers/SPEAKER_00", json={"participant_id": person}
    )
    assert response.status_code == 404
    task = (await client.get(f"{PREFIX}/tasks", params={"meeting_id": mid})).json()[0]
    assert (
        await client.patch(
            f"{PREFIX}/tasks/{task['id']}", json={"responsible_participant_id": person}
        )
    ).status_code == 404


async def test_delete_participant_clears_links_and_stales_analysis(env):
    client = env["client"]
    mid, processor, people = await analyzed_meeting(env)
    assert (
        await client.delete(f"{PREFIX}/meetings/{mid}/participants/{people[1]}")
    ).status_code == 204
    transcript = (await client.get(f"{PREFIX}/meetings/{mid}/transcript")).json()
    assert transcript[1]["speaker_name"] is None
    task = (await client.get(f"{PREFIX}/tasks", params={"meeting_id": mid})).json()[0]
    assert task["responsible_participant_id"] is None
    assert task["responsible_name"] is None
    assert (await client.get(f"{PREFIX}/meetings/{mid}/exports/pdf")).status_code == 409
    assert processor.transcription.transcribe.call_count == 1


async def test_exports_unicode_and_markup_are_data(env):
    client = env["client"]
    mid, _, _ = await analyzed_meeting(env)
    task = (await client.get(f"{PREFIX}/tasks", params={"meeting_id": mid})).json()[0]
    await client.patch(
        f"{PREFIX}/tasks/{task['id']}",
        json={"description": "Қазақша: Ә Ғ Қ Ң Ө Ұ Ү Һ І <script>& отчёт"},
    )
    pdf = await client.get(f"{PREFIX}/meetings/{mid}/exports/pdf")
    assert pdf.status_code == 200, pdf.text[:200] if pdf.status_code != 200 else ""
    text = " ".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert "Ә Ғ Қ Ң Ө Ұ Ү Һ І" in text
    assert "<script>&" in text
    docx = await client.get(f"{PREFIX}/meetings/{mid}/exports/docx")
    assert docx.status_code == 200
    text = "\n".join(p.text for p in Document(BytesIO(docx.content)).paragraphs)
    assert "Қазақша" in text and "Ерлан" in text
    assert len(list(env["settings"].storage_dir.rglob("protocol-*"))) == 2


async def test_failure_is_visible_and_retry_works(env):
    client = env["client"]
    mid = (await upload(env)).json()["id"]
    processor = fake_processor(env)
    processor.audio.extract.side_effect = PipelineError("INVALID_OR_UNSUPPORTED_MEDIA")
    await run_next(env, processor)
    meeting = (await client.get(f"{PREFIX}/meetings/{mid}")).json()
    assert meeting["status"] == "FAILED"
    assert meeting["error_code"] == "INVALID_OR_UNSUPPORTED_MEDIA"
    processor.audio.extract.side_effect = None
    assert (await client.post(f"{PREFIX}/meetings/{mid}/process")).status_code == 202
    await run_next(env, processor)
    assert (await client.get(f"{PREFIX}/meetings/{mid}")).json()["status"] == "AWAITING_MAPPING"


async def test_expired_lease_is_reclaimed_and_old_worker_fenced(env):
    await upload(env)
    jobs = JobService(env["factory"], env["settings"])
    jid, owner = await jobs.claim()
    async with env["factory"]() as session, session.begin():
        job = await session.get(Job, jid)
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    replacement_id, replacement_owner = await jobs.claim()
    assert replacement_id == jid and replacement_owner != owner
    with pytest.raises(LeaseLost):
        await jobs.stage(jid, owner, "INVALID_WRITE")
    assert await jobs.heartbeat(jid, owner) is False
    assert await jobs.heartbeat(jid, replacement_owner) is True


async def test_worker_retry_limit(env):
    mid = (await upload(env)).json()["id"]
    jobs = JobService(env["factory"], env["settings"])
    jid, _ = await jobs.claim()
    async with env["factory"]() as session, session.begin():
        job = await session.get(Job, jid)
        job.attempts = env["settings"].job_max_attempts
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    assert await jobs.claim() is None
    meeting = (await env["client"].get(f"{PREFIX}/meetings/{mid}")).json()
    assert meeting["error_code"] == "WORKER_RETRY_LIMIT"


@pytest.mark.postgres
async def test_postgres_workers_claim_distinct_jobs(env):
    if not env["postgres"]:
        pytest.skip("Set TEST_DATABASE_URL to exercise SKIP LOCKED on PostgreSQL")
    import asyncio

    await upload(env)
    await upload(env)
    jobs = JobService(env["factory"], env["settings"])
    a, b = await asyncio.gather(jobs.claim(), jobs.claim())
    assert a and b and a[0] != b[0]
    async with env["factory"]() as session:
        running = (await session.scalars(select(Job).where(Job.status == JobStatus.RUNNING))).all()
        assert len(running) == 2


async def test_task_filters_and_overdue_do_not_change_completed(env):
    client = env["client"]
    mid, _, people = await analyzed_meeting(env)
    task = (await client.get(f"{PREFIX}/tasks", params={"meeting_id": mid})).json()[0]
    await client.patch(
        f"{PREFIX}/tasks/{task['id']}",
        json={"deadline": "2000-01-01T00:00:00Z", "status": "IN_PROGRESS"},
    )
    response = await client.get(
        f"{PREFIX}/tasks",
        params={
            "status": "OVERDUE",
            "responsible_id": people[1],
            "deadline_to": "2001-01-01T00:00:00Z",
        },
    )
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "OVERDUE"
    await client.patch(f"{PREFIX}/tasks/{task['id']}", json={"status": "COMPLETED"})
    assert (await client.get(f"{PREFIX}/tasks", params={"status": "OVERDUE"})).json() == []
    assert (await client.get(f"{PREFIX}/tasks", params={"status": "COMPLETED"})).json()[0][
        "completed_at"
    ]
    assert (
        await client.patch(f"{PREFIX}/tasks/{task['id']}", json={"description": None})
    ).status_code == 422
    assert (await client.patch(f"{PREFIX}/tasks/{task['id']}", json={})).status_code == 422
    assert (
        await client.patch(f"{PREFIX}/tasks/{task['id']}", json={"deadline": "2026-01-01T00:00:00"})
    ).status_code == 422
    async with env["factory"]() as session:
        persisted = await session.get(Task, UUID(task["id"]))
        assert persisted.completed_at is not None


async def test_silent_audio_completes_without_llm(env):
    client = env["client"]
    mid = (await upload(env)).json()["id"]
    processor = fake_processor(env)
    processor.transcription.transcribe.return_value.segments = []
    await run_next(env, processor)
    await client.post(f"{PREFIX}/meetings/{mid}/analyze", json={})
    await run_next(env, processor)
    assert processor.extraction.llm.contexts == []
    assert (await client.get(f"{PREFIX}/meetings/{mid}")).json()["status"] == "COMPLETED"


async def test_remapping_stales_analysis_without_stt(env):
    client = env["client"]
    mid, processor, people = await prepared_meeting(env)
    await client.patch(
        f"{PREFIX}/meetings/{mid}/speakers/SPEAKER_00", json={"participant_id": people[1]}
    )
    assert (await client.get(f"{PREFIX}/meetings/{mid}/transcript")).json()[0][
        "speaker_name"
    ] == "Айдар"
    assert processor.transcription.transcribe.call_count == 1
