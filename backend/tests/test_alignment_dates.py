from datetime import datetime

import pytest

from app.schemas.transcript import DiarizationSegment, SpeechSegment
from app.services.transcript_merge_service import TranscriptMergeService
from app.utils.dates import end_of_day, parse_deadline


def test_overlap_beats_matching_start():
    speech = [SpeechSegment(start=0, end=10, text="Длинная реплика")]
    turns = [
        DiarizationSegment(start=0, end=1, speaker="A"),
        DiarizationSegment(start=1, end=10, speaker="B"),
    ]
    assert TranscriptMergeService().merge(speech, turns)[0].speaker_id == "B"


def test_cumulative_overlap_is_not_double_counted():
    speech = [SpeechSegment(start=0, end=10, text="Қазақша сөйлеу")]
    turns = [
        DiarizationSegment(start=0, end=3, speaker="A"),
        DiarizationSegment(start=7, end=10, speaker="A"),
        DiarizationSegment(start=3, end=7, speaker="B"),
        DiarizationSegment(start=3, end=7, speaker="B"),
    ]
    assert TranscriptMergeService().merge(speech, turns)[0].speaker_id == "A"


def test_unknown_and_deterministic_tie():
    speech = [
        SpeechSegment(start=0, end=4, text="Первый"),
        SpeechSegment(start=10, end=11, text="Второй"),
    ]
    turns = [
        DiarizationSegment(start=0, end=2, speaker="B"),
        DiarizationSegment(start=2, end=4, speaker="A"),
    ]
    result = TranscriptMergeService().merge(speech, turns)
    assert [segment.speaker_id for segment in result] == ["A", "UNKNOWN"]


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("до пятницы", "2026-09-25"),
        ("завтра", "2026-09-24"),
        ("послезавтра", "2026-09-25"),
        ("через неделю", "2026-09-30"),
        ("25 сентября", "2026-09-25"),
        ("келесі дүйсенбіге дейін", "2026-09-28"),
        ("жұмаға дейін", "2026-09-25"),
        ("ертең", "2026-09-24"),
        ("бір аптадан кейін", "2026-09-30"),
        ("25 қыркүйек", "2026-09-25"),
        ("3 күннен кейін", "2026-09-26"),
        ("через 3 дня", "2026-09-26"),
        ("25.09.2026", "2026-09-25"),
        ("2026-09-25", "2026-09-25"),
        ("как-нибудь", None),
        (None, None),
        ("31 февраля", None),
    ],
)
def test_deadline_uses_meeting_date(phrase, expected):
    result = parse_deadline(
        phrase, datetime.fromisoformat("2026-09-23T10:00:00+05:00"), "Asia/Almaty"
    )
    assert (result.isoformat() if result else None) == expected


def test_deadline_respects_local_midnight_and_next_week():
    reference = datetime.fromisoformat("2026-09-27T22:00:00+00:00")  # Monday, Sep 28 in Kazakhstan.
    result = parse_deadline("келесі дүйсенбіге дейін", reference, "Asia/Almaty")
    assert result.isoformat() == "2026-10-05"
    assert end_of_day(result, "Asia/Almaty").isoformat() == "2026-10-05T18:59:59+00:00"
