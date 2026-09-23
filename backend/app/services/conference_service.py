import asyncio
import hashlib
import secrets
from collections import defaultdict
from uuid import UUID

from fastapi import HTTPException, WebSocket
from sqlalchemy import func, select

from app.api.tasks import serialize_task
from app.db.base import utcnow
from app.models import Meeting, Participant, Task
from app.models.conference import AudioChunk, Conference, ConferenceMember, ConferenceMessage
from app.repositories.meeting_repository import MeetingRepository
from app.utils.dates import aware_utc


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


async def authorize(session, room_id: UUID, token: str, host=False):
    room = await session.get(Conference, room_id)
    member = await session.scalar(
        select(ConferenceMember).where(
            ConferenceMember.conference_id == room_id,
            ConferenceMember.token_hash == token_hash(token),
        )
    )
    if not room or not member:
        raise HTTPException(403, "Нет доступа к конференции. Откройте ссылку приглашения.")
    if host and not member.is_host:
        raise HTTPException(403, "Это действие доступно только организатору.")
    return room, member


async def snapshot(session, room, member, hub):
    meeting = await session.get(Meeting, room.id)
    participants = (
        await session.execute(
            select(Participant, ConferenceMember)
            .join(ConferenceMember, ConferenceMember.id == Participant.id)
            .where(Participant.meeting_id == room.id)
        )
    ).all()
    transcript = await MeetingRepository(session).transcript(room.id)
    tasks = (
        await session.scalars(
            select(Task).where(Task.meeting_id == room.id).order_by(Task.created_at)
        )
    ).all()
    counts = dict(
        (
            await session.execute(
                select(AudioChunk.status, func.count())
                .where(AudioChunk.conference_id == room.id)
                .group_by(AudioChunk.status)
            )
        ).all()
    )
    messages = (
        await session.execute(
            select(ConferenceMessage, Participant.name)
            .join(Participant, Participant.id == ConferenceMessage.member_id)
            .where(ConferenceMessage.conference_id == room.id)
            .order_by(ConferenceMessage.created_at.desc())
            .limit(100)
        )
    ).all()
    peers = hub.peers(str(room.id))
    return {
        "id": str(room.id),
        "title": meeting.title,
        "date": aware_utc(meeting.meeting_date).isoformat(),
        "created_at": aware_utc(room.created_at).isoformat(),
        "server_time": utcnow().isoformat(),
        "started_at": aware_utc(room.started_at or room.created_at).isoformat(),
        "me": str(member.id),
        "is_host": member.is_host,
        "recording": room.recording,
        "recording_version": room.recording_version,
        "ended_at": aware_utc(room.ended_at).isoformat() if room.ended_at else None,
        "analysis_status": room.analysis_status,
        "analysis_error": room.analysis_error,
        "analysis_version": meeting.analysis_version,
        "analysis_stale": meeting.analysis_stale,
        "summary": meeting.summary or "",
        "topics": meeting.topics,
        "decisions": meeting.decisions,
        "audio": {
            "pending": counts.get("pending", 0) + counts.get("processing", 0),
            "done": counts.get("done", 0),
            "failed": counts.get("failed", 0),
        },
        "participants": [
            {
                "id": str(p.id),
                "name": p.name,
                "is_host": m.is_host,
                "online": str(p.id) in peers,
                **peers.get(str(p.id), {}).get("media", {}),
            }
            for p, m in participants
        ],
        "transcript": sorted(transcript, key=lambda s: (s["start"], s["ordinal"])),
        "tasks": [serialize_task(t).model_dump(mode="json") for t in tasks],
        "messages": [
            {
                "id": str(m.id),
                "member_id": str(m.member_id),
                "name": name,
                "text": m.text,
                "at": aware_utc(m.created_at).isoformat(),
            }
            for m, name in reversed(messages)
        ],
    }


class ConferenceHub:
    """One signaling process. Media travels directly over authenticated room membership."""

    def __init__(self):
        self.rooms = defaultdict(dict)
        self.locks = defaultdict(asyncio.Lock)

    def peers(self, room_id):
        return self.rooms.get(room_id, {})

    async def send(self, peer, message):
        try:
            async with peer["lock"]:
                await asyncio.wait_for(peer["socket"].send_json(message), timeout=5)
        except (TimeoutError, RuntimeError, OSError):
            pass

    async def broadcast(self, room_id, message, exclude=None):
        await asyncio.gather(
            *(
                self.send(peer, message)
                for key, peer in list(self.peers(room_id).items())
                if key != exclude
            )
        )

    async def connect(self, room_id, member_id, name, socket: WebSocket, maximum):
        async with self.locks[room_id]:
            peers = self.rooms[room_id]
            old = peers.get(member_id)
            if not old and len(peers) >= maximum:
                await socket.close(code=4009, reason="В конференции уже максимум участников")
                return False
            if old:
                await old["socket"].close(code=4000, reason="Открыта другая вкладка")
            await socket.send_json(
                {
                    "type": "welcome",
                    "self": member_id,
                    "peers": [
                        {"id": k, "name": p["name"], **p["media"]}
                        for k, p in peers.items()
                        if k != member_id
                    ],
                }
            )
            peers[member_id] = {
                "socket": socket,
                "lock": asyncio.Lock(),
                "name": name,
                "media": {"muted": False, "camera": False, "sharing": False},
            }
        await self.broadcast(
            room_id, {"type": "peer-joined", "id": member_id, "name": name}, member_id
        )
        return True

    async def disconnect(self, room_id, member_id, socket):
        peers = self.peers(room_id)
        if peers.get(member_id, {}).get("socket") is socket:
            del peers[member_id]
            await self.broadcast(room_id, {"type": "peer-left", "id": member_id})
        if not peers:
            self.rooms.pop(room_id, None)
