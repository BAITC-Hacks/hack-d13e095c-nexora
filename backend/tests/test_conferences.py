import asyncio
import io
import wave
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.base import utcnow
from app.live_worker import LiveProcessor
from app.models.conference import AudioChunk, Conference, ConferenceRecording
from app.schemas.analysis import MeetingAnalysis
from app.services.speech_client import LiveSpeechResult

BASE = "/api/v1/conferences"
QUOTE = "Айдар, подготовь отчёт до пятницы."


def wav(seconds=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        f.writeframes(b"\x10\x00" * int(seconds * 16000))
    return buf.getvalue()


def headers(room):
    return {"Authorization": "Bearer " + room["token"]}


async def create(env, name="Ерлан"):
    r = await env["client"].post(
        BASE, json={"title": "Тестовая конференция", "name": name, "consent": True}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def start(env, host):
    path = BASE + "/" + host["room"]["id"]
    r = await env["client"].post(path + "/recording", headers=headers(host), json={"enabled": True})
    assert r.status_code == 200, r.text
    return path, r.json()["recording_version"]


async def audio(env, host, path, version, sequence=None, content=None, offset=0):
    return await env["client"].post(
        path + "/audio",
        headers={**headers(host), "Content-Type": "audio/wav"},
        params={"sequence": str(sequence or uuid4()), "version": version, "start": offset},
        content=content if content is not None else wav(),
    )


async def test_room_invites_consent_and_host_authority(env):
    client = env["client"]
    assert (
        await client.post(BASE, json={"title": "A", "name": "B", "consent": False})
    ).status_code == 422
    host = await create(env)
    path = BASE + "/" + host["room"]["id"]
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers={"Authorization": "Bearer invalid"})).status_code == 403
    assert (
        await client.post(
            path + "/join", json={"invite": "x" * 32, "name": "Айдар", "consent": True}
        )
    ).status_code == 403
    response = await client.post(
        path + "/join", json={"invite": host["invite"], "name": "Айдар", "consent": True}
    )
    assert response.status_code == 200, response.text
    guest = response.json()
    assert guest["room"]["is_host"] is False
    assert len(guest["room"]["participants"]) == 2
    assert (
        await client.post(path + "/recording", headers=headers(guest), json={"enabled": True})
    ).status_code == 403
    assert (await client.post(path + "/end", headers=headers(guest))).status_code == 403
    assert (await client.post(path + "/end", headers=headers(host))).status_code == 200
    assert (
        await client.post(
            path + "/join", json={"invite": host["invite"], "name": "Late", "consent": True}
        )
    ).status_code == 409
    assert (await client.get(path, headers=headers(guest))).status_code == 200


async def test_create_access_key_is_not_required_by_invitees(env):
    env["settings"].conference_access_key = "test-create-key"
    r = await env["client"].post(BASE, json={"title": "Test", "name": "Host", "consent": True})
    assert r.status_code == 401
    r = await env["client"].post(
        BASE,
        headers={"X-Conference-Key": "test-create-key"},
        json={"title": "Test", "name": "Host", "consent": True},
    )
    assert r.status_code == 201
    room = r.json()
    joined = await env["client"].post(
        f"{BASE}/{room['room']['id']}/join",
        json={"name": "Guest", "invite": room["invite"], "consent": True},
    )
    assert joined.status_code == 200


async def test_audio_requires_recording_validates_format_and_is_idempotent(env):
    host = await create(env)
    path = BASE + "/" + host["room"]["id"]
    assert (await audio(env, host, path, 0)).status_code == 409
    path, version = await start(env, host)
    sequence = uuid4()
    r = await audio(env, host, path, version, sequence)
    assert r.status_code == 202, r.text
    assert (await audio(env, host, path, version, sequence)).json()["id"] == r.json()["id"]
    assert (await audio(env, host, path, version, content=b"bad")).status_code == 422
    assert (await audio(env, host, path, version, offset=-1)).status_code == 422
    assert (await audio(env, host, path, version, offset=10000)).status_code == 422
    assert (await audio(env, host, path, version, content=b"a" * 512001)).status_code == 413
    async with env["factory"]() as session:
        chunks = (await session.scalars(select(AudioChunk))).all()
        assert len(chunks) == 1
    outsider = await create(env, "Other")
    assert (await audio(env, outsider, path, version)).status_code == 403


async def test_durable_browser_retry_accepts_old_consented_recording_epoch(env):
    host = await create(env)
    path, version = await start(env, host)
    await env["client"].post(path + "/recording", headers=headers(host), json={"enabled": False})
    async with env["factory"]() as session:
        room = await session.get(Conference, UUID(host["room"]["id"]))
        room.started_at = utcnow() - timedelta(seconds=100)
        epoch = await session.scalar(select(ConferenceRecording))
        epoch.started_at = room.started_at
        epoch.stopped_at = room.started_at + timedelta(seconds=10)
        await session.commit()
    await start(env, host)  # new epoch must not invalidate buffered audio from an older epoch
    assert (await audio(env, host, path, version, offset=3)).status_code == 202
    assert (await audio(env, host, path, version, offset=20)).status_code == 422


class Speech:
    async def transcribe(self, path):
        assert path.read_bytes().startswith(b"RIFF")
        return LiveSpeechResult(segments=[{"start": 0, "end": 0.9, "text": QUOTE}], language="ru")


class LLM:
    async def analyze(self, context):
        segment = context["transcript"][0]
        return MeetingAnalysis.model_validate(
            {
                "summary": "Обсудили подготовку отчёта.",
                "topics": ["Отчёт"],
                "decisions": [],
                "tasks": [
                    {
                        "description": "Подготовить отчёт",
                        "responsible_name": "Айдар",
                        "responsible_speaker_id": None,
                        "assigned_by": segment["speaker_name"],
                        "deadline_raw": "до пятницы",
                        "deadline": None,
                        "priority": "high",
                        "confidence": 0.95,
                        "source_segment_ids": [segment["ordinal"]],
                        "source_quote": QUOTE,
                    }
                ],
            }
        )


async def test_real_pipeline_wiring_speaker_mapping_tasks_exports_and_edits(env):
    host = await create(env)
    path, version = await start(env, host)
    guest = (
        await env["client"].post(
            path + "/join", json={"name": "Айдар", "invite": host["invite"], "consent": True}
        )
    ).json()
    assert (await audio(env, host, path, version)).status_code == 202
    processor = LiveProcessor(env["factory"], env["settings"], speech=Speech(), llm=LLM())
    assert await processor.speech_once()
    assert await processor.analysis_once()
    state = (await env["client"].get(path, headers=headers(guest))).json()
    assert state["transcript"][0]["speaker_name"] == "Ерлан"
    task = state["tasks"][0]
    assert task["responsible_participant_id"] == guest["room"]["me"]
    assert task["deadline"] and task["source_quote"] == QUOTE
    assert state["audio"] == {"pending": 0, "done": 1, "failed": 0}
    assert (
        await env["client"].get(path + "/exports/pdf", headers=headers(host))
    ).status_code == 409
    edited = await env["client"].patch(
        path + "/tasks/" + task["id"],
        headers=headers(host),
        json={"description": "Уточнённое поручение", "status": "COMPLETED"},
    )
    assert edited.status_code == 200, edited.text
    await env["client"].post(path + "/end", headers=headers(host))
    async with env["factory"]() as session:
        room = await session.get(Conference, UUID(state["id"]))
        room.analysis_at = utcnow() - timedelta(seconds=60)
        room.recording_stopped_at = utcnow() - timedelta(seconds=20)
        await session.commit()
    assert await processor.analysis_once()
    updated = (await env["client"].get(path, headers=headers(host))).json()
    assert len(updated["tasks"]) == 1
    assert updated["tasks"][0]["description"] == "Уточнённое поручение"
    assert updated["tasks"][0]["status"] == "COMPLETED"
    for fmt, prefix in [("pdf", b"%PDF"), ("docx", b"PK")]:
        r = await env["client"].get(path + "/exports/" + fmt, headers=headers(host))
        assert r.status_code == 200, r.text[:200]
        assert r.content.startswith(prefix)
    r = await env["client"].get(path + "/recording.wav", headers=headers(guest))
    assert r.status_code == 200 and r.content.startswith(b"RIFF")
    with wave.open(io.BytesIO(r.content)) as f:
        assert f.getnframes() == 16000


async def test_signaling_two_members_chat_and_cross_room_isolation(env):
    host = await create(env)
    path = BASE + "/" + host["room"]["id"]
    guest = (
        await env["client"].post(
            path + "/join", json={"invite": host["invite"], "name": "Айдар", "consent": True}
        )
    ).json()

    def connect_two():
        with TestClient(env["app"]) as client:
            with client.websocket_connect(path + "/ws") as a:
                a.send_json({"type": "auth", "token": host["token"]})
                assert a.receive_json()["type"] == "welcome"
                with client.websocket_connect(path + "/ws") as b:
                    b.send_json({"type": "auth", "token": guest["token"]})
                    welcome = b.receive_json()
                    assert welcome["peers"][0]["id"] == host["room"]["me"]
                    assert a.receive_json()["type"] == "peer-joined"
                    a.send_json(
                        {
                            "type": "signal",
                            "to": guest["room"]["me"],
                            "data": {"description": {"type": "offer", "sdp": "test"}},
                        }
                    )
                    relayed = b.receive_json()
                    assert relayed["from"] == host["room"]["me"]
                    assert relayed["data"]["description"]["sdp"] == "test"
                    b.send_json({"type": "chat", "text": "Сәлем, команда"})
                    assert b.receive_json()["type"] == "room-updated"
                    assert a.receive_json()["type"] == "room-updated"
                    a.send_json({"type": "media", "muted": True, "camera": False})
                    assert b.receive_json()["muted"] is True
                assert a.receive_json()["type"] == "peer-left"

    await asyncio.to_thread(connect_two)
    state = (await env["client"].get(path, headers=headers(host))).json()
    assert state["messages"][0]["text"] == "Сәлем, команда"
    assert all(not p["online"] for p in state["participants"])


async def test_no_cross_room_task_edit(env):
    # A foreign task UUID must never be forwarded to the unscoped admin endpoint.
    host, outsider = await create(env), await create(env)
    path, _ = await start(env, host)
    assert (
        await env["client"].patch(
            path + "/tasks/" + str(uuid4()), headers=headers(outsider), json={"status": "COMPLETED"}
        )
    ).status_code == 403
