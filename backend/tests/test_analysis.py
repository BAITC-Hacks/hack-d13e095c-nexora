import json
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.schemas.analysis import MeetingAnalysis
from app.services.llm_service import LLMService
from app.services.task_extraction_service import TaskExtractionService, extraction_key
from app.utils.errors import PipelineError
from tests.helpers import QUOTE, FakeLLM


def transcript():
    return [
        {
            "ordinal": 0,
            "speaker_id": "SPEAKER_00",
            "speaker_name": "Ерлан",
            "start": 0,
            "end": 4,
            "text": QUOTE,
        },
        {
            "ordinal": 1,
            "speaker_id": "SPEAKER_01",
            "speaker_name": "Айдар",
            "start": 5,
            "end": 8,
            "text": "Жақсы, дайындаймын.",
        },
    ]


async def test_evidence_checks_and_deterministic_deadline():
    settings = Settings(_env_file=None)
    service = TaskExtractionService(settings, FakeLLM())
    parts = await service.extract(
        transcript(), datetime.fromisoformat("2026-09-23T00:00:00+05:00"), "Asia/Almaty"
    )
    task = parts[0].tasks[0]
    assert task.deadline.isoformat() == "2026-09-25"
    assert task.responsible_name == "Айдар"
    task.source_quote = "Сфабрикованное поручение"
    assert (
        service.validate_evidence(parts[0], transcript(), datetime.now(), "Asia/Almaty").tasks == []
    )


async def test_invented_names_and_missing_deadline_are_null():
    service = TaskExtractionService(Settings(_env_file=None), FakeLLM())
    analysis = await service.llm.analyze({})
    task = analysis.tasks[0]
    task.responsible_name = "Несуществующий"
    task.responsible_speaker_id = "SPEAKER_99"
    task.assigned_by = "Выдуманный"
    task.deadline_raw = "в следующем году"
    validated = service.validate_evidence(
        analysis, transcript(), datetime.now(), "Asia/Almaty"
    ).tasks[0]
    assert validated.responsible_name is None and validated.responsible_speaker_id is None
    assert validated.assigned_by is None and validated.deadline is None
    assert validated.confidence <= 0.5


async def test_nonexistent_source_is_rejected():
    service = TaskExtractionService(Settings(_env_file=None), FakeLLM())
    analysis = await service.llm.analyze({})
    analysis.tasks[0].source_segment_ids = [99]
    assert not service.validate_evidence(
        analysis, transcript(), datetime.now(), "Asia/Almaty"
    ).tasks


def test_long_transcript_is_chunked_without_data_loss():
    service = TaskExtractionService(Settings(_env_file=None, llm_chunk_chars=1000), FakeLLM())
    segments = [{"ordinal": i, "text": "Слово " * 80} for i in range(10)]
    chunks = service.chunks(segments)
    assert len(chunks) > 1
    assert {s["ordinal"] for chunk in chunks for s in chunk} == set(range(10))
    with pytest.raises(PipelineError, match="TRANSCRIPT_SEGMENT_TOO_LONG"):
        service.chunks([{"ordinal": 0, "text": "a" * 1001}])


async def test_structured_ollama_request(monkeypatch):
    analysis = await FakeLLM().analyze({})
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"model_info": {}})
        return httpx.Response(
            200, json={"done": True, "message": {"content": analysis.model_dump_json()}}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr("app.services.llm_service.httpx.AsyncClient", lambda **kwargs: client)
    llm = LLMService(Settings(_env_file=None))
    monkeypatch.setattr(
        llm, "_local_origin", AsyncMock(return_value=("http://127.0.0.1:11434", "localhost:11434"))
    )
    result = await llm.analyze({"MEETING_LOCAL_DATE": "2026-09-23", "transcript": transcript()})
    assert isinstance(result, MeetingAnalysis)
    payload = json.loads(calls[-1].content)
    assert payload["format"] == MeetingAnalysis.model_json_schema()
    assert payload["stream"] is False and payload["think"] is False
    assert "Never invent" in payload["messages"][0]["content"]
    assert "2026-09-23" in payload["messages"][1]["content"]


async def test_dns_to_public_ip_is_rejected(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 11434))],
    )
    with pytest.raises(PipelineError, match="NONLOCAL"):
        await LLMService(Settings(_env_file=None))._local_origin()


async def test_requester_is_not_automatically_assignee():
    service = TaskExtractionService(Settings(_env_file=None), FakeLLM())
    analysis = await service.llm.analyze({})
    analysis.tasks[0].responsible_name = "Ерлан"
    analysis.tasks[0].responsible_speaker_id = "SPEAKER_00"
    task = service.validate_evidence(analysis, transcript(), datetime.now(), "Asia/Almaty").tasks[0]
    assert task.responsible_name is None and task.responsible_speaker_id is None


async def test_another_speakers_acceptance_does_not_assign_the_requester():
    service = TaskExtractionService(Settings(_env_file=None), FakeLLM())
    analysis = await service.llm.analyze({})
    task = analysis.tasks[0]
    task.source_segment_ids = [0, 1]
    task.source_quote = " ".join(s["text"] for s in transcript())
    task.responsible_name, task.responsible_speaker_id = "Ерлан", "SPEAKER_00"
    task = service.validate_evidence(analysis, transcript(), datetime.now(), "Asia/Almaty").tasks[0]
    assert task.responsible_name is None and task.responsible_speaker_id is None


async def test_two_tasks_with_shared_evidence_remain_distinct():
    task = (await FakeLLM().analyze({})).tasks[0]
    second = task.model_copy(update={"description": "Согласовать бюджет"})
    assert extraction_key(task) != extraction_key(second)


async def test_cloud_alias_rejected_before_transcript_sent(monkeypatch):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"remote_host": "https://ollama.com"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr("app.services.llm_service.httpx.AsyncClient", lambda **kwargs: client)
    llm = LLMService(Settings(_env_file=None))
    monkeypatch.setattr(
        llm, "_local_origin", AsyncMock(return_value=("http://127.0.0.1:11434", "localhost:11434"))
    )
    with pytest.raises(PipelineError, match="CLOUD_MODEL_BLOCKED"):
        await llm.analyze({"transcript": transcript()})
    assert len(calls) == 1 and calls[0].url.path == "/api/show"
    assert QUOTE.encode() not in calls[0].content
