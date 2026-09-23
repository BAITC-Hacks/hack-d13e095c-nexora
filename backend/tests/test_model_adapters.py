import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.services.diarization_service import DiarizationService
from app.services.transcription_service import TranscriptionService
from app.utils.errors import PipelineError


def test_whisper_is_offline_multilingual_and_preserves_word_times(tmp_path, monkeypatch):
    model_dir = tmp_path / "whisper"
    model_dir.mkdir()
    (model_dir / "model.bin").touch()
    model = Mock()
    model.transcribe.return_value = (
        iter(
            [
                SimpleNamespace(
                    words=[SimpleNamespace(start=1.0, end=2.0, word=" Қазақша")],
                    start=1,
                    end=2,
                    text="Қазақша",
                )
            ]
        ),
        SimpleNamespace(language="kk", duration=3.0),
    )
    constructor = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=constructor))
    settings = Settings(_env_file=None, whisper_model_dir=model_dir)
    result = TranscriptionService(settings).transcribe(tmp_path / "meeting.wav")
    assert constructor.call_args.kwargs["local_files_only"] is True
    assert model.transcribe.call_args.kwargs["language"] is None
    assert model.transcribe.call_args.kwargs["multilingual"] is True
    assert model.transcribe.call_args.kwargs["word_timestamps"] is True
    assert result.detected_language == "kk" and result.segments[0].text == "Қазақша"
    assert result.segments[0].start == 1.0


def test_missing_weights_fail_without_network(tmp_path):
    settings = Settings(_env_file=None, whisper_model_dir=tmp_path, diarization_model_dir=tmp_path)
    with pytest.raises(PipelineError, match="WHISPER_MODEL_MISSING"):
        TranscriptionService(settings).transcribe(tmp_path / "meeting.wav")
    with pytest.raises(PipelineError, match="DIARIZATION_MODEL_MISSING"):
        DiarizationService(settings).diarize(tmp_path / "meeting.wav")
