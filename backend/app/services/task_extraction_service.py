import hashlib
import re
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from app.config import Settings
from app.schemas.analysis import MeetingAnalysis
from app.services.llm_service import LLMService
from app.utils.dates import aware_utc, parse_deadline
from app.utils.errors import PipelineError


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def extraction_key(task) -> str:
    # Distinct assignments from the same sentence must not collapse into a single task.
    identity = f"{sorted(set(task.source_segment_ids))}:{normalized(task.source_quote)}:{normalized(task.description)}"
    return hashlib.sha256(identity.encode()).hexdigest()


class TaskExtractionService:
    def __init__(self, settings: Settings, llm: LLMService):
        self.settings, self.llm = settings, llm

    def chunks(self, transcript: list[dict]) -> list[list[dict]]:
        chunks, current, size = [], [], 0
        for segment in transcript:
            # Never silently discard an oversized segment or truncate an entire meeting.
            if len(segment["text"]) > self.settings.llm_chunk_chars:
                raise PipelineError("TRANSCRIPT_SEGMENT_TOO_LONG")
            length = len(segment["text"]) + 160
            if current and size + length > self.settings.llm_chunk_chars:
                chunks.append(current)
                overlap = (
                    current[-1:]
                    if len(current[-1]["text"]) + length + 320 < self.settings.llm_chunk_chars
                    else []
                )
                current = overlap.copy()
                size = sum(len(item["text"]) + 160 for item in current)
            current.append(segment)
            size += length
        if current:
            chunks.append(current)
        return chunks

    def validate_evidence(
        self,
        analysis: MeetingAnalysis,
        transcript: list[dict],
        meeting_date: datetime,
        timezone: str,
    ) -> MeetingAnalysis:
        by_id = {segment["ordinal"]: segment for segment in transcript}

        def evidence(item):
            if not all(index in by_id for index in item.source_segment_ids):
                return None
            selected = [by_id[index] for index in sorted(set(item.source_segment_ids))]
            text = " ".join(segment["text"] for segment in selected)
            if normalized(item.source_quote) not in normalized(text):
                return None
            return selected

        validated = []
        for task in analysis.tasks:
            selected = evidence(task)
            if not selected:
                continue
            quote = normalized(task.source_quote)
            speaker_names = {
                segment["speaker_id"]: segment["speaker_name"] for segment in transcript
            }
            if (
                task.responsible_speaker_id not in speaker_names
                or task.responsible_speaker_id == "UNKNOWN"
            ):
                task.responsible_speaker_id = None
            mapped_name = speaker_names.get(task.responsible_speaker_id)
            # A requester is not an assignee just because they uttered the task.
            # Infer self-assignment only from explicit first-person commitment verbs.
            commitment = re.compile(
                r"(?<!не )\b(сделаю|подготовлю|отправлю|проверю|выполню|пришлю|согласую|"
                r"беру на себя|дайындаймын|жасаймын|жіберемін|тексеремін|орындаймын)\b",
            )
            speaker_supported = bool(commitment.search(quote)) and any(
                s["speaker_id"] == task.responsible_speaker_id
                and commitment.search(normalized(s["text"]))
                for s in selected
            )
            name_supported = bool(mapped_name and normalized(mapped_name) in quote)
            if mapped_name and (name_supported or speaker_supported):
                if task.responsible_name and normalized(task.responsible_name) not in {
                    normalized(mapped_name),
                    "",
                }:
                    task.responsible_speaker_id = None
                else:
                    task.responsible_name = mapped_name
            elif not speaker_supported:
                task.responsible_speaker_id = None
                mapped_name = None
            if (
                task.responsible_name
                and normalized(task.responsible_name) not in quote
                and task.responsible_name != mapped_name
            ):
                task.responsible_name = None
                task.confidence = min(task.confidence, 0.5)
            allowed_authors = {s["speaker_name"] for s in selected if s["speaker_name"]}
            if (
                task.assigned_by not in allowed_authors
                and task.assigned_by
                and normalized(task.assigned_by) not in quote
            ):
                task.assigned_by = None
            if task.deadline_raw and normalized(task.deadline_raw) not in quote:
                task.deadline_raw = None
            task.deadline = parse_deadline(task.deadline_raw, meeting_date, timezone)
            validated.append(task)
        analysis.tasks = validated
        analysis.decisions = [item for item in analysis.decisions if evidence(item)]
        memory = []
        for item in analysis.memory_objects:
            if not evidence(item) or normalized(item.name) not in normalized(item.source_quote):
                continue
            if normalized(item.name) in {
                "проект",
                "project",
                "документ",
                "document",
                "отчёт",
                "отчет",
                "договор",
                "протокол",
                "жоба",
                "құжат",
            }:
                continue
            if item.url:
                try:
                    parsed = urlsplit(item.url)
                    safe = (
                        parsed.scheme in {"http", "https"}
                        and parsed.hostname
                        and not parsed.username
                        and not parsed.password
                    )
                except ValueError:
                    safe = False
                if not safe or item.url not in item.source_quote:
                    item.url = None
            memory.append(item)
        analysis.memory_objects = memory
        return analysis

    async def extract(
        self, transcript: list[dict], meeting_date: datetime, timezone: str
    ) -> list[MeetingAnalysis]:
        result = []
        for chunk in self.chunks(transcript):
            context = {
                "MEETING_LOCAL_DATE": aware_utc(meeting_date)
                .astimezone(ZoneInfo(timezone))
                .isoformat(),
                "TIMEZONE": timezone,
                "transcript": chunk,
            }
            analysis = await self.llm.analyze(context)
            result.append(self.validate_evidence(analysis, chunk, meeting_date, timezone))
        return result
