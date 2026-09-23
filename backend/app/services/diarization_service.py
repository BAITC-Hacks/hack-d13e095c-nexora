import os
from pathlib import Path

from app.config import Settings
from app.schemas.transcript import DiarizationSegment
from app.utils.errors import PipelineError


class DiarizationService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def diarize(self, audio_path: Path) -> list[DiarizationSegment]:
        model_path = self.settings.diarization_model_dir.resolve()
        if not (model_path / "config.yaml").is_file():
            raise PipelineError("DIARIZATION_MODEL_MISSING")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        os.environ["PYANNOTE_METRICS_ENABLED"] = "0"
        import soundfile as sf
        import torch
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(str(model_path))
        pipeline.to(torch.device(self.settings.ai_device))
        try:
            waveform, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
            output = pipeline(
                {"waveform": torch.from_numpy(waveform.T), "sample_rate": sample_rate}
            )
            annotation = output.exclusive_speaker_diarization
            return [
                DiarizationSegment(speaker=speaker, start=max(0, turn.start), end=turn.end)
                for turn, _, speaker in annotation.itertracks(yield_label=True)
                if turn.end > max(0, turn.start)
            ]
        finally:
            del pipeline
            if self.settings.ai_device == "cuda":
                torch.cuda.empty_cache()
