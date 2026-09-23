import asyncio
import io
import json
import secrets
import time
import wave
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import Config, Session
from app.db.base import utcnow
from app.models import Meeting, Participant, Speaker, Task
from app.models.conference import (
    AudioChunk,
    Conference,
    ConferenceMember,
    ConferenceMessage,
    ConferenceRecording,
)
from app.models.enums import MeetingStatus
from app.schemas.task import TaskPatch
from app.services.conference_service import authorize, new_token, snapshot, token_hash
from app.utils.dates import aware_utc

router = APIRouter(prefix="/api/v1/conferences", tags=["conferences"])


def bearer(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Откройте конференцию по ссылке приглашения.")
    return authorization[7:]


Token = Annotated[str, Depends(bearer)]


class CreateRoom(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1, max_length=100)
    consent: Literal[True]
    scheduled_at: AwareDatetime | None = None


class JoinRoom(BaseModel):
    invite: str = Field(min_length=20, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    consent: Literal[True]


async def add_member(session, room_id, name, host=False):
    if not name.strip():
        raise HTTPException(422, "Укажите имя")
    member_id, token = uuid4(), new_token()
    session.add(
        Participant(
            id=member_id,
            meeting_id=room_id,
            name=name.strip(),
            position="Организатор" if host else None,
        )
    )
    await session.flush()
    member = ConferenceMember(
        id=member_id,
        conference_id=room_id,
        token_hash=token_hash(token),
        is_host=host,
        consent_at=utcnow(),
    )
    session.add(member)
    session.add(Speaker(meeting_id=room_id, speaker_id=str(member_id), participant_id=member_id))
    await session.flush()
    return member, token


@router.post("", status_code=201)
async def create_room(
    body: CreateRoom,
    session: Session,
    settings: Config,
    request: Request,
    x_conference_key: Annotated[str | None, Header()] = None,
):
    if settings.conference_access_key and not secrets.compare_digest(
        x_conference_key or "", settings.conference_access_key
    ):
        raise HTTPException(401, "Неверный ключ создания конференций")
    if not body.title.strip():
        raise HTTPException(422, "Укажите тему")
    room_id, invite = uuid4(), new_token()
    session.add(
        Meeting(
            id=room_id,
            title=body.title.strip(),
            meeting_date=body.scheduled_at or utcnow(),
            timezone=settings.meeting_timezone,
            status=MeetingStatus.PROCESSING,
            stage="LIVE",
            original_path="",
            original_filename="conference",
            mime_type="audio/wav",
            file_size=0,
        )
    )
    await session.flush()
    room = Conference(id=room_id, invite_hash=token_hash(invite))
    session.add(room)
    await session.flush()
    member, token = await add_member(session, room_id, body.name, True)
    await session.commit()
    return {
        "token": token,
        "invite": invite,
        "room": await snapshot(session, room, member, request.app.state.conference_hub),
    }


@router.post("/{room_id}/join")
async def join_room(room_id: UUID, body: JoinRoom, session: Session, request: Request):
    room = await session.scalar(
        select(Conference).where(Conference.id == room_id).with_for_update()
    )
    if not room or not secrets.compare_digest(room.invite_hash, token_hash(body.invite)):
        raise HTTPException(403, "Ссылка приглашения недействительна")
    if room.ended_at:
        raise HTTPException(409, "Конференция завершена")
    # Bound persisted identities as well as active WebRTC peers.
    count = await session.scalar(
        select(func.count())
        .select_from(ConferenceMember)
        .where(ConferenceMember.conference_id == room_id)
    )
    if count >= 100:
        raise HTTPException(409, "Достигнут лимит регистраций в этой конференции")
    member, token = await add_member(session, room_id, body.name)
    await session.commit()
    return {
        "token": token,
        "room": await snapshot(session, room, member, request.app.state.conference_hub),
    }


@router.get("/{room_id}")
async def get_room(room_id: UUID, token: Token, session: Session, request: Request):
    room, member = await authorize(session, room_id, token)
    return await snapshot(session, room, member, request.app.state.conference_hub)


@router.get("/{room_id}/rtc")
async def rtc_config(room_id: UUID, token: Token, session: Session, settings: Config):
    await authorize(session, room_id, token)
    return {"iceServers": settings.rtc_ice_servers, "maxPeers": settings.conference_max_peers}


class RecordingBody(BaseModel):
    enabled: bool


@router.post("/{room_id}/recording")
async def recording(
    room_id: UUID, body: RecordingBody, token: Token, session: Session, request: Request
):
    room, member = await authorize(session, room_id, token, host=True)
    await session.refresh(room, with_for_update=True)
    if room.ended_at:
        raise HTTPException(409, "Конференция завершена")
    if room.recording != body.enabled:
        room.recording = body.enabled
        if body.enabled:
            room.started_at = room.started_at or utcnow()
            room.recording_version += 1
            room.recording_started_at = utcnow()
            room.recording_stopped_at = None
            session.add(
                ConferenceRecording(
                    conference_id=room_id,
                    version=room.recording_version,
                    started_at=room.recording_started_at,
                )
            )
        else:
            room.recording_stopped_at = utcnow()
            room.analysis_requested = True
            epoch = await session.scalar(
                select(ConferenceRecording).where(
                    ConferenceRecording.conference_id == room_id,
                    ConferenceRecording.version == room.recording_version,
                )
            )
            if epoch:
                epoch.stopped_at = room.recording_stopped_at
    await session.commit()
    await request.app.state.conference_hub.broadcast(str(room_id), {"type": "room-updated"})
    return await snapshot(session, room, member, request.app.state.conference_hub)


@router.post("/{room_id}/end")
async def end_room(room_id: UUID, token: Token, session: Session, request: Request):
    room, member = await authorize(session, room_id, token, host=True)
    room.ended_at = room.ended_at or utcnow()
    room.recording = False
    room.recording_stopped_at = room.ended_at
    room.analysis_requested = True
    epoch = await session.scalar(
        select(ConferenceRecording).where(
            ConferenceRecording.conference_id == room_id,
            ConferenceRecording.version == room.recording_version,
        )
    )
    if epoch:
        epoch.stopped_at = epoch.stopped_at or room.ended_at
    await session.commit()
    await request.app.state.conference_hub.broadcast(str(room_id), {"type": "ended"})
    return await snapshot(session, room, member, request.app.state.conference_hub)


@router.post("/{room_id}/analyze", status_code=202)
async def analyze_room(room_id: UUID, token: Token, session: Session):
    room, _ = await authorize(session, room_id, token, host=True)
    room.analysis_requested = True
    room.analysis_error = None
    return {"status": "queued"}


@router.post("/{room_id}/retry", status_code=202)
async def retry_audio(room_id: UUID, token: Token, session: Session):
    from sqlalchemy import update

    await authorize(session, room_id, token, host=True)
    await session.execute(
        update(AudioChunk)
        .where(AudioChunk.conference_id == room_id, AudioChunk.status == "failed")
        .values(status="pending", attempts=0, error=None)
    )
    return {"status": "queued"}


@router.post("/{room_id}/audio", status_code=202)
async def upload_chunk(
    room_id: UUID,
    token: Token,
    session: Session,
    request: Request,
    settings: Config,
    sequence: UUID,
    start: float,
    version: int,
):
    import math

    room, member = await authorize(session, room_id, token)
    # Serialize uploads per room, ensuring retries cannot create duplicate queue entries.
    await session.refresh(room, with_for_update=True)
    existing = await session.scalar(
        select(AudioChunk).where(
            AudioChunk.member_id == member.id, AudioChunk.sequence == str(sequence)
        )
    )
    if existing:
        return {"id": str(existing.id), "status": existing.status}
    now = utcnow()
    epoch = await session.scalar(
        select(ConferenceRecording).where(
            ConferenceRecording.conference_id == room_id, ConferenceRecording.version == version
        )
    )
    if not epoch:
        raise HTTPException(409, "Запись не включена организатором")
    anchor = aware_utc(room.started_at or room.created_at)
    elapsed = (now - anchor).total_seconds()
    lower = (aware_utc(epoch.started_at) - anchor).total_seconds()
    if (
        not math.isfinite(start)
        or start < max(0, lower - 3)
        or start > elapsed + 3
        or start > settings.max_audio_seconds
    ):
        raise HTTPException(422, "Некорректное время аудиофрагмента")
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > 512_000:
            raise HTTPException(413, "Фрагмент должен быть короче 15 секунд")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (
                1,
                2,
                16000,
                "NONE",
            ):
                raise ValueError()
            duration = wav.getnframes() / 16000
            if (
                not 0.05 <= duration <= 15
                or len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2
            ):
                raise ValueError()
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(422, "Ожидается WAV PCM16 mono 16kHz, до 15 секунд") from None
    upper = (aware_utc(epoch.stopped_at) - anchor).total_seconds() if epoch.stopped_at else elapsed
    if start + duration > upper + 3:
        raise HTTPException(422, "Аудио вне согласованного интервала записи")
    pending = await session.scalar(
        select(func.count())
        .select_from(AudioChunk)
        .where(
            AudioChunk.conference_id == room_id, AudioChunk.status.in_(["pending", "processing"])
        )
    )
    if pending >= 500:
        raise HTTPException(429, "Распознавание не успевает. Аудио ожидает отправки на устройстве.")
    path = settings.storage_dir / str(room_id) / "live" / f"{uuid4()}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, data)
    chunk = AudioChunk(
        conference_id=room_id,
        member_id=member.id,
        sequence=str(sequence),
        start=start,
        duration=duration,
        path=str(path),
    )
    session.add(chunk)
    # Export is gated by queued chunks; only recognized new text makes analysis stale.
    try:
        await session.commit()
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"id": str(chunk.id), "status": "pending"}


@router.patch("/{room_id}/tasks/{task_id}")
async def edit_task(room_id: UUID, task_id: UUID, body: TaskPatch, token: Token, session: Session):
    from app.api.tasks import patch_task

    await authorize(session, room_id, token)
    task = await session.get(Task, task_id)
    if not task or task.meeting_id != room_id:
        raise HTTPException(404, "Поручение не найдено")
    return await patch_task(task_id, body, session)


@router.get("/{room_id}/exports/{format}")
async def export_room(
    room_id: UUID, format: Literal["pdf", "docx"], token: Token, session: Session, settings: Config
):
    from app.api.exports import export

    room, _ = await authorize(session, room_id, token)
    pending = await session.scalar(
        select(func.count())
        .select_from(AudioChunk)
        .where(
            AudioChunk.conference_id == room_id, AudioChunk.status.in_(["pending", "processing"])
        )
    )
    failed = await session.scalar(
        select(func.count())
        .select_from(AudioChunk)
        .where(AudioChunk.conference_id == room_id, AudioChunk.status == "failed")
    )
    if (
        room.recording
        or pending
        or failed
        or room.analysis_requested
        or room.analysis_status == "analyzing"
    ):
        raise HTTPException(
            409, "Остановите запись и дождитесь обработки аудио и итогового анализа"
        )
    return await export(room_id, format, session, settings)


@router.get("/{room_id}/diagnostics")
async def diagnostics(room_id: UUID, token: Token, session: Session, settings: Config):
    import httpx

    from app.services.llm_service import LLMService
    from app.services.speech_client import SpeechClient

    await authorize(session, room_id, token)
    heartbeat = settings.storage_dir / "live-worker.heartbeat"
    worker = heartbeat.is_file() and time.time() - heartbeat.stat().st_mtime < 30
    result = {
        "speech": False,
        "ollama": False,
        "worker": worker,
        "speech_error": None,
        "ollama_error": None,
    }
    try:
        result["speech"] = await SpeechClient(settings).ready()
    except Exception:
        result["speech_error"] = "Сервис распознавания недоступен или модель не загружена"
    try:
        origin, host = await LLMService(settings)._local_origin()
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.post(
                origin + "/api/show", headers={"Host": host}, json={"model": settings.ollama_model}
            )
            body = response.json()
            result["ollama"] = (
                response.status_code == 200
                and not body.get("remote_host")
                and not body.get("remote_model")
            )
    except Exception:
        result["ollama_error"] = "Проверьте OLLAMA_URL, модель и доступность другого ПК"
    return result


@router.get("/{room_id}/recording.wav")
async def download_audio(room_id: UUID, token: Token, session: Session, settings: Config):
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    from app.services.live_audio_export import mix_recording

    room, _ = await authorize(session, room_id, token)
    if room.recording:
        raise HTTPException(409, "Сначала остановите запись")
    chunks = (
        await session.scalars(
            select(AudioChunk).where(AudioChunk.conference_id == room_id).order_by(AudioChunk.start)
        )
    ).all()
    if not chunks:
        raise HTTPException(404, "Аудиозаписи пока нет")
    path = settings.storage_dir / str(room_id) / f"recording-{uuid4()}.wav"
    await asyncio.to_thread(mix_recording, [(c.path, c.start) for c in chunks], path)
    return FileResponse(
        path,
        media_type="audio/wav",
        filename="conference.wav",
        background=BackgroundTask(path.unlink, missing_ok=True),
        headers={"Cache-Control": "no-store"},
    )


@router.websocket("/{room_id}/ws")
async def signaling(websocket: WebSocket, room_id: UUID):
    from urllib.parse import urlsplit

    # Browser websocket requests must originate from this application origin.
    origin = websocket.headers.get("origin")
    if origin and urlsplit(origin).netloc != websocket.headers.get("host"):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    hub, factory = websocket.app.state.conference_hub, websocket.app.state.session_factory
    member_id = None
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), 10)
        if (
            auth.get("type") != "auth"
            or not isinstance(auth.get("token"), str)
            or len(auth["token"]) > 100
        ):
            raise HTTPException(403, "Invalid auth")
        async with factory() as session:
            room, member = await authorize(session, room_id, auth["token"])
            if room.ended_at:
                await websocket.close(code=4004, reason="Конференция завершена")
                return
            person = await session.get(Participant, member.id)
            if room.started_at is None:
                room.started_at = utcnow()
                await session.commit()
            member_id = str(member.id)
            if not await hub.connect(
                str(room_id),
                member_id,
                person.name,
                websocket,
                websocket.app.state.settings.conference_max_peers,
            ):
                return
        budget_start, messages = time.monotonic(), 0
        while True:
            raw = await asyncio.wait_for(websocket.receive_text(), 60)
            messages += 1
            if time.monotonic() - budget_start > 10:
                budget_start, messages = time.monotonic(), 1
            if len(raw) > 65536 or messages > 200:
                await websocket.close(code=1008)
                break
            body = json.loads(raw)
            if not isinstance(body, dict):
                continue
            kind = body.get("type")
            if kind == "ping":
                await hub.send(hub.peers(str(room_id))[member_id], {"type": "pong"})
            elif kind == "signal" and isinstance(body.get("to"), str):
                peer = hub.peers(str(room_id)).get(body["to"])
                if peer:
                    await hub.send(
                        peer, {"type": "signal", "from": member_id, "data": body.get("data")}
                    )
            elif kind == "media":
                media = {k: bool(body.get(k)) for k in ("muted", "camera", "sharing")}
                hub.peers(str(room_id))[member_id]["media"] = media
                await hub.broadcast(
                    str(room_id), {"type": "media", "id": member_id, **media}, member_id
                )
            elif (
                kind == "chat"
                and isinstance(body.get("text"), str)
                and 0 < len(body["text"].strip()) <= 2000
            ):
                async with factory() as session:
                    room = await session.get(Conference, room_id)
                    if room.ended_at:
                        continue
                    session.add(
                        ConferenceMessage(
                            conference_id=room_id,
                            member_id=UUID(member_id),
                            text=body["text"].strip(),
                        )
                    )
                    await session.commit()
                await hub.broadcast(str(room_id), {"type": "room-updated"})
    except (TimeoutError, WebSocketDisconnect, HTTPException, ValueError, KeyError, RuntimeError):
        try:
            await websocket.close(code=1008)
        except RuntimeError:
            pass
    finally:
        if member_id:
            await hub.disconnect(str(room_id), member_id, websocket)
