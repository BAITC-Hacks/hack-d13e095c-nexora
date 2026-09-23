from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import String, case, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import Task
from app.models.enums import TaskStatus
from app.utils.dates import aware_utc


def effective_status(task: Task, now: datetime | None = None) -> TaskStatus:
    now = now or utcnow()
    if task.status in {TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE}:
        if task.deadline and aware_utc(task.deadline) < now:
            return TaskStatus.OVERDUE
        if task.status == TaskStatus.OVERDUE:
            return TaskStatus.NEW
    return task.status


def status_expression(now: datetime):
    active = Task.status.in_([TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE])
    return case(
        (active & (Task.deadline < now), TaskStatus.OVERDUE.value),
        (Task.status == TaskStatus.OVERDUE, TaskStatus.NEW.value),
        else_=cast(Task.status, String),
    )


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, task_id: UUID) -> Task:
        task = await self.session.get(Task, task_id)
        if task is None:
            raise HTTPException(404, "Task not found")
        return task

    async def list(
        self,
        *,
        status=None,
        meeting_id=None,
        responsible_id=None,
        deadline_from=None,
        deadline_to=None,
        offset=0,
        limit=100,
    ):
        query = select(Task)
        if status:
            query = query.where(status_expression(utcnow()) == status.value)
        if meeting_id:
            query = query.where(Task.meeting_id == meeting_id)
        if responsible_id:
            query = query.where(Task.responsible_participant_id == responsible_id)
        if deadline_from:
            query = query.where(Task.deadline >= deadline_from)
        if deadline_to:
            query = query.where(Task.deadline <= deadline_to)
        return (
            await self.session.scalars(
                query.order_by(Task.created_at.desc(), Task.id).offset(offset).limit(limit)
            )
        ).all()
