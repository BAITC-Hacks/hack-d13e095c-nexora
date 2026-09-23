from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime

from app.api.deps import Session
from app.db.base import utcnow
from app.models.enums import TaskStatus
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.participant_repository import ParticipantRepository
from app.repositories.task_repository import TaskRepository, effective_status
from app.schemas.task import TaskPatch, TaskRead
from app.utils.dates import aware_utc

router = APIRouter(prefix="/tasks", tags=["tasks"])


def serialize_task(task) -> TaskRead:
    return TaskRead.model_validate(task).model_copy(update={"status": effective_status(task)})


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    session: Session,
    status: TaskStatus | None = None,
    meeting_id: UUID | None = None,
    responsible_id: UUID | None = None,
    deadline_from: AwareDatetime | None = None,
    deadline_to: AwareDatetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    if deadline_from and deadline_to and deadline_from > deadline_to:
        raise HTTPException(422, "deadline_from must be <= deadline_to")
    tasks = await TaskRepository(session).list(
        status=status,
        meeting_id=meeting_id,
        responsible_id=responsible_id,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        offset=offset,
        limit=limit,
    )
    return [serialize_task(task) for task in tasks]


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: UUID, session: Session):
    return serialize_task(await TaskRepository(session).get(task_id))


@router.patch("/{task_id}", response_model=TaskRead)
async def patch_task(task_id: UUID, body: TaskPatch, session: Session):
    task = await TaskRepository(session).get(task_id)
    await MeetingRepository(session).editable(task.meeting_id)
    await session.refresh(task)
    values = body.model_dump(exclude_unset=True)
    if "responsible_participant_id" in values:
        participant_id = values["responsible_participant_id"]
        participant = (
            await ParticipantRepository(session).get(task.meeting_id, participant_id)
            if participant_id
            else None
        )
        task.responsible_name = participant.name if participant else None
        task.responsible_speaker_id = None
    if "deadline" in values:
        task.deadline_raw = None
    for name, value in values.items():
        setattr(task, name, value)
    if task.status == TaskStatus.OVERDUE and (
        task.deadline is None or aware_utc(task.deadline) >= utcnow()
    ):
        if body.status == TaskStatus.OVERDUE:
            raise HTTPException(422, "OVERDUE requires a past deadline")
        task.status = TaskStatus.NEW
    if task.status == TaskStatus.COMPLETED:
        task.completed_at = task.completed_at or utcnow()
    else:
        task.completed_at = None
    task.edited_by_user = True
    await session.flush()
    return serialize_task(task)
