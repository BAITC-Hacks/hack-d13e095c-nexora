from typing import Literal

from pydantic import Field

from app.schemas.common import Schema


class BriefingItem(Schema):
    category: Literal["risk", "decision", "question"]
    text: str = Field(min_length=1, max_length=220)
    previous_id: str | None
    previous_quote: str | None = Field(max_length=500)
    current_id: str | None
    current_quote: str | None = Field(max_length=500)


class BriefingAnalysis(Schema):
    items: list[BriefingItem] = Field(max_length=5)
