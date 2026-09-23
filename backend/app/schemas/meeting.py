from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from app.models.enums import JobKind, JobStatus, MeetingStatus
from app.schemas.common import Schema


class MeetingCreate(Schema):
    title: str = Field(min_length=1, max_length=300)
    meeting_date: AwareDatetime
    timezone: str = "Asia/Almaty"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class MeetingRead(Schema):
    id: UUID
    title: str
    meeting_date: datetime
    timezone: str
    status: MeetingStatus
    stage: str
    original_filename: str
    file_size: int
    detected_language: str | None
    processing_time: float | None
    stt_model: str | None
    duration: float | None
    summary: str | None
    topics: list[str]
    decisions: list[str]
    analysis_stale: bool
    analysis_version: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class AnalyzeRequest(Schema):
    allow_unmapped: bool = False


class JobRead(Schema):
    id: UUID
    meeting_id: UUID
    kind: JobKind
    status: JobStatus
    attempts: int
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
