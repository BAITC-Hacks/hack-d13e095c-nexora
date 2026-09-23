from unittest.mock import Mock

from app.schemas.analysis import MeetingAnalysis
from app.schemas.transcript import DiarizationSegment, SpeechSegment, TranscriptionResult
from app.services.job_service import JobService
from app.services.meeting_processor import MeetingProcessor
from app.worker import run_job

PREFIX = "/api/v1"
QUOTE = "Айдар, подготовь отчёт до пятницы."
WAV_HEADER = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVE" + b"test"


async def upload(env, filename="meeting.wav", content=WAV_HEADER, mime="audio/wav", **fields):
    return await env["client"].post(
        PREFIX + "/meetings",
        data={
            "title": "Жоба — рабочее совещание",
            "meeting_date": "2026-09-23T10:00:00+05:00",
            "timezone": "Asia/Almaty",
            **fields,
        },
        files={"file": (filename, content, mime)},
    )


class FakeLLM:
    def __init__(self):
        self.contexts = []

    async def analyze(self, context):
        self.contexts.append(context)
        return MeetingAnalysis.model_validate(
            {
                "summary": "Обсудили подготовку отчёта.",
                "topics": ["Отчёт"],
                "decisions": [],
                "tasks": [
                    {
                        "description": "Подготовить отчёт",
                        "responsible_name": "Айдар",
                        "responsible_speaker_id": "SPEAKER_01",
                        "assigned_by": "Ерлан",
                        "deadline_raw": "до пятницы",
                        "deadline": "2099-01-01",
                        "priority": "normal",
                        "confidence": 0.95,
                        "source_segment_ids": [0],
                        "source_quote": QUOTE,
                    }
                ],
            }
        )


def fake_processor(env):
    audio = Mock()
    audio.extract.return_value = 12.0
    transcription = Mock()
    transcription.transcribe.return_value = TranscriptionResult(
        segments=[
            SpeechSegment(start=0, end=4, text=QUOTE),
            SpeechSegment(start=5, end=8, text="Жақсы, дайындаймын."),
        ],
        detected_language="ru",
        processing_time=1,
        model="large-v3",
        duration=12,
    )
    diarization = Mock()
    diarization.diarize.return_value = [
        DiarizationSegment(start=0, end=4, speaker="SPEAKER_00"),
        DiarizationSegment(start=5, end=8, speaker="SPEAKER_01"),
    ]
    llm = FakeLLM()
    return MeetingProcessor(
        env["factory"],
        env["settings"],
        audio=audio,
        transcription=transcription,
        diarization=diarization,
        llm=llm,
    )


async def run_next(env, processor):
    jobs = JobService(env["factory"], env["settings"])
    claim = await jobs.claim()
    assert claim is not None
    await run_job(processor, jobs, *claim)


async def prepared_meeting(env):
    response = await upload(env)
    assert response.status_code == 202, response.text
    meeting_id = response.json()["id"]
    processor = fake_processor(env)
    await run_next(env, processor)
    participant_ids = []
    for index, name in enumerate(["Ерлан", "Айдар"]):
        response = await env["client"].post(
            f"{PREFIX}/meetings/{meeting_id}/participants", json={"name": name}
        )
        assert response.status_code == 201, response.text
        participant_ids.append(response.json()["id"])
        response = await env["client"].patch(
            f"{PREFIX}/meetings/{meeting_id}/speakers/SPEAKER_0{index}",
            json={"participant_id": participant_ids[-1]},
        )
        assert response.status_code == 200, response.text
    return meeting_id, processor, participant_ids


async def analyzed_meeting(env):
    meeting_id, processor, participants = await prepared_meeting(env)
    response = await env["client"].post(f"{PREFIX}/meetings/{meeting_id}/analyze", json={})
    assert response.status_code == 202, response.text
    await run_next(env, processor)
    return meeting_id, processor, participants
