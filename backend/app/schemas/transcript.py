from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import Schema


class SpeechSegment(Schema):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class DiarizationSegment(Schema):
    speaker: str
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class MergedSegment(SpeechSegment):
    speaker_id: str


class TranscriptRead(MergedSegment):
    id: UUID
    ordinal: int
    speaker_name: str | None


class TranscriptionResult(Schema):
    segments: list[SpeechSegment]
    detected_language: str
    processing_time: float
    model: str
    duration: float
