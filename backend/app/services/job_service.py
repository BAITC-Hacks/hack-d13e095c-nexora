from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update

from app.config import Settings
from app.db.base import utcnow
from app.models import Job, Meeting
from app.models.enums import JobKind, JobStatus, MeetingStatus
from app.utils.dates import aware_utc
from app.utils.errors import LeaseLost


class JobService:
    def __init__(self, factory, settings: Settings):
        self.factory, self.settings = factory, settings

    async def claim(self) -> tuple[UUID, str] | None:
        async with self.factory() as session, session.begin():
            now = utcnow()
            expired = (
                await session.scalars(
                    select(Job)
                    .where(
                        Job.status == JobStatus.RUNNING,
                        Job.lease_until < now,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for job in expired:
                job.owner = None
                job.lease_until = None
                if job.attempts >= self.settings.job_max_attempts:
                    job.status, job.error_code, job.finished_at = (
                        JobStatus.FAILED,
                        "WORKER_RETRY_LIMIT",
                        now,
                    )
                    meeting = await session.get(Meeting, job.meeting_id)
                    meeting.status, meeting.error_code, meeting.stage = (
                        MeetingStatus.FAILED,
                        job.error_code,
                        "FAILED",
                    )
                else:
                    job.status = JobStatus.PENDING
            await session.flush()
            job = await session.scalar(
                select(Job)
                .where(Job.status == JobStatus.PENDING)
                .order_by(Job.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not job:
                return None
            job.status, job.owner = JobStatus.RUNNING, str(uuid4())
            job.attempts += 1
            job.lease_until = now + timedelta(seconds=self.settings.job_lease_seconds)
            return job.id, job.owner

    async def heartbeat(self, job_id: UUID, owner: str) -> bool:
        async with self.factory() as session, session.begin():
            result = await session.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.owner == owner,
                    Job.status == JobStatus.RUNNING,
                    Job.lease_until > utcnow(),
                )
                .values(lease_until=utcnow() + timedelta(seconds=self.settings.job_lease_seconds))
            )
            return result.rowcount == 1

    @asynccontextmanager
    async def fenced(self, job_id: UUID, owner: str):
        async with self.factory() as session, session.begin():
            job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if (
                not job
                or job.owner != owner
                or job.status != JobStatus.RUNNING
                or not job.lease_until
                or aware_utc(job.lease_until) <= utcnow()
            ):
                raise LeaseLost()
            meeting = await session.scalar(
                select(Meeting).where(Meeting.id == job.meeting_id).with_for_update()
            )
            yield session, meeting, job

    async def stage(self, job_id: UUID, owner: str, stage: str):
        async with self.fenced(job_id, owner) as (_, meeting, job):
            meeting.stage = stage
            meeting.status = (
                MeetingStatus.PROCESSING
                if job.kind == JobKind.TRANSCRIBE
                else MeetingStatus.ANALYZING
            )

    async def fail(self, job_id: UUID, owner: str, code: str):
        async with self.fenced(job_id, owner) as (_, meeting, job):
            job.status, job.error_code, job.finished_at = JobStatus.FAILED, code, utcnow()
            job.lease_until = None
            meeting.status, meeting.stage, meeting.error_code = MeetingStatus.FAILED, "FAILED", code

    @staticmethod
    def succeed(meeting: Meeting, job: Job, status: MeetingStatus):
        job.status, job.finished_at, job.lease_until = JobStatus.SUCCEEDED, utcnow(), None
        meeting.status, meeting.stage, meeting.error_code = status, status.value, None
