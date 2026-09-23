from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.conferences import Token
from app.api.deps import Session
from app.db.base import utcnow
from app.models.briefing import ConferenceBriefing
from app.services.briefing_service import inputs, result_payload
from app.services.conference_service import authorize
from app.utils.dates import aware_utc

router = APIRouter(prefix="/api/v1/conferences", tags=["what-changed"])


class BriefingSetup(BaseModel):
    previous_id: UUID
    previous_token: str = Field(min_length=20, max_length=100, repr=False)
    updates: str = Field(default="", max_length=2000)
    share_with_participants: bool = False


async def configure(session, room, body):
    if room.ended_at:
        raise HTTPException(409, "Встреча завершена")
    if room.id == body.previous_id:
        raise HTTPException(422, "Выберите другую встречу")
    if not body.share_with_participants:
        raise HTTPException(
            422, "Подтвердите доступ участников новой встречи к сводке прошлого созвона"
        )
    previous, _ = await authorize(session, body.previous_id, body.previous_token, host=True)
    if not previous.ended_at:
        raise HTTPException(409, "Сначала завершите предыдущую встречу")
    if aware_utc(previous.created_at) >= aware_utc(room.created_at):
        raise HTTPException(422, "Предыдущая встреча должна быть создана раньше текущей")
    briefing = await session.get(ConferenceBriefing, room.id)
    if not briefing:
        briefing = ConferenceBriefing(id=room.id, requested_at=utcnow())
        session.add(briefing)
    else:
        briefing.revision += 1
    briefing.previous_id, briefing.updates = previous.id, body.updates.strip()
    briefing.status, briefing.error, briefing.requested_at = "pending", None, utcnow()
    briefing.result, briefing.input_hash = None, None
    await session.flush()
    return briefing


@router.put("/{room_id}/briefing", status_code=202)
async def set_briefing(room_id: UUID, body: BriefingSetup, token: Token, session: Session):
    room, _ = await authorize(session, room_id, token, host=True)
    await session.refresh(room, with_for_update=True)
    await configure(session, room, body)
    return {"status": "pending"}


class BriefingUpdates(BaseModel):
    updates: str = Field(max_length=2000)


@router.patch("/{room_id}/briefing", status_code=202)
async def edit_briefing(room_id: UUID, body: BriefingUpdates, token: Token, session: Session):
    room, _ = await authorize(session, room_id, token, host=True)
    await session.refresh(room, with_for_update=True)
    if room.ended_at:
        raise HTTPException(409, "Встреча завершена")
    briefing = await session.scalar(
        select(ConferenceBriefing).where(ConferenceBriefing.id == room_id).with_for_update()
    )
    if not briefing:
        raise HTTPException(404, "Сначала выберите прошлую встречу")
    briefing.updates = body.updates.strip()
    briefing.revision += 1
    briefing.status, briefing.error, briefing.requested_at = "pending", None, utcnow()
    return {"status": "pending"}


@router.get("/{room_id}/briefing")
async def get_briefing(room_id: UUID, token: Token, session: Session):
    room, member = await authorize(session, room_id, token)
    briefing = await session.get(ConferenceBriefing, room_id)
    if not briefing:
        return {"configured": False}
    data = await inputs(session, briefing)
    stale = data is None or data["hash"] != briefing.input_hash
    result = briefing.result
    # Never mix new deterministic deadlines with old model conclusions.
    if stale:
        result = result_payload(data, []) if data else None
    return {
        "configured": True,
        "status": briefing.status,
        "stale": stale,
        "error": briefing.error,
        "result": result,
        "updates": briefing.updates if member.is_host else None,
        "previous_id": str(briefing.previous_id) if briefing.previous_id else None,
        "generated_at": briefing.generated_at,
        "requested_at": briefing.requested_at,
    }
