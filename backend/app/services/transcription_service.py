import os
from pathlib import Path
from time import perf_counter

from app.config import Settings
from app.schemas.transcript import SpeechSegment, TranscriptionResult
from app.utils.errors import PipelineError


class TranscriptionService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        if not (self.settings.whisper_model_dir / "model.bin").is_file():
            raise PipelineError("WHISPER_MODEL_MISSING")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from faster_whisper import WhisperModel

        started = perf_counter()
        model = WhisperModel(
            str(self.settings.whisper_model_dir.resolve()),
            device=self.settings.ai_device,
            compute_type=self.settings.whisper_compute_type,
            cpu_threads=self.settings.whisper_cpu_threads,
            local_files_only=True,
        )
        try:
            segments, info = model.transcribe(
                str(audio_path),
                language=None,
                task="transcribe",
                multilingual=True,
                beam_size=5,
                vad_filter=True,
                word_timestamps=True,
                condition_on_previous_text=False,
            )
            # Keep word-sized intervals for accurate speaker boundaries and code switching.
            speech = []
            for segment in segments:
                words = segment.words or []
                units = words if words else [segment]
                for unit in units:
                    text = (unit.word if words else unit.text).strip()
                    if text and unit.end > unit.start:
                        speech.append(SpeechSegment(start=unit.start, end=unit.end, text=text))
            return TranscriptionResult(
                segments=speech,
                detected_language=info.language,
                processing_time=perf_counter() - started,
                model=self.settings.whisper_model,
                duration=info.duration,
            )
        finally:
            # Release CTranslate2 GPU memory before loading pyannote / Ollama.
            del model
