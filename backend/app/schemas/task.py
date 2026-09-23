from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.models.enums import Priority, TaskStatus
from app.schemas.common import PatchSchema, Schema


class TaskPatch(PatchSchema):
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    responsible_participant_id: UUID | None = None
    deadline: AwareDatetime | None = None
    priority: Priority | None = None
    status: TaskStatus | None = None

    @model_validator(mode="after")
    def nonnullable(self):
        for name in ("description", "priority", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class TaskRead(Schema):
    id: UUID
    meeting_id: UUID
    description: str
    responsible_participant_id: UUID | None
    responsible_name: str | None
    responsible_speaker_id: str | None
    assigned_by: str | None
    deadline: datetime | None
    deadline_raw: str | None
    status: TaskStatus
    priority: Priority
    confidence: float
    source_transcript_start: float | None
    source_transcript_end: float | None
    source_quote: str
    analysis_version: int
    edited_by_user: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
