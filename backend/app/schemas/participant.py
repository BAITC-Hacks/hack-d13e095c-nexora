from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field, model_validator

from app.schemas.common import PatchSchema, Schema


class ParticipantCreate(Schema):
    name: str = Field(min_length=1, max_length=200)
    position: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None


class ParticipantPatch(PatchSchema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    position: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None

    @model_validator(mode="after")
    def required_name(self):
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class ParticipantRead(ParticipantCreate):
    id: UUID
    meeting_id: UUID
    created_at: datetime


class SpeakerPatch(Schema):
    participant_id: UUID | None


class SpeakerRead(Schema):
    speaker_id: str
    participant_id: UUID | None
    speaker_name: str | None
