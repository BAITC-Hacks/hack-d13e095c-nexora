from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.common import Schema


class ExtractedTask(Schema):
    description: str = Field(min_length=1, max_length=4000)
    responsible_name: str | None
    responsible_speaker_id: str | None
    assigned_by: str | None
    deadline_raw: str | None
    deadline: date | None
    priority: Literal["low", "normal", "high", "urgent"]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    source_segment_ids: list[int] = Field(min_length=1, max_length=20)
    source_quote: str = Field(min_length=1, max_length=4000)


class SupportedDecision(Schema):
    description: str = Field(min_length=1, max_length=4000)
    source_segment_ids: list[int] = Field(min_length=1)
    source_quote: str = Field(min_length=1, max_length=4000)


class MeetingAnalysis(Schema):
    summary: str = Field(max_length=10000)
    topics: list[str] = Field(max_length=30)
    decisions: list[SupportedDecision] = Field(max_length=100)
    tasks: list[ExtractedTask] = Field(max_length=200)
