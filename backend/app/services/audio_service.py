import json
import subprocess
from pathlib import Path

from app.config import Settings
from app.utils.errors import PipelineError


class AudioService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _run(self, args: list[str], timeout: int) -> str:
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, errors="replace", timeout=timeout, check=False
            )
        except FileNotFoundError as exc:
            raise PipelineError("FFMPEG_NOT_INSTALLED") from exc
        except subprocess.TimeoutExpired as exc:
            raise PipelineError("MEDIA_PROCESSING_TIMEOUT") from exc
        if result.returncode:
            raise PipelineError("INVALID_OR_UNSUPPORTED_MEDIA")
        return result.stdout

    def extract(self, source: Path, destination: Path) -> float:
        metadata = self._run(
            [
                self.settings.ffprobe_binary,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_entries",
                "format=duration:stream=codec_type",
                "-of",
                "json",
                str(source),
            ],
            timeout=60,
        )
        try:
            info = json.loads(metadata)
            if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
                raise PipelineError("NO_AUDIO_STREAM")
            duration = float(info.get("format", {}).get("duration", 0))
        except (ValueError, TypeError) as exc:
            raise PipelineError("INVALID_MEDIA_METADATA") from exc
        if duration > self.settings.max_audio_seconds:
            raise PipelineError("AUDIO_DURATION_LIMIT")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".partial.wav")
        try:
            self._run(
                [
                    self.settings.ffmpeg_binary,
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-i",
                    str(source),
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    "-map_metadata",
                    "-1",
                    "-t",
                    str(self.settings.max_audio_seconds + 1),
                    str(temporary),
                ],
                self.settings.ffmpeg_timeout_seconds,
            )
            import wave

            with wave.open(str(temporary), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
            if duration > self.settings.max_audio_seconds:
                raise PipelineError("AUDIO_DURATION_LIMIT")
            if duration <= 0:
                raise PipelineError("EMPTY_AUDIO")
            temporary.replace(destination)
            return duration
        finally:
            temporary.unlink(missing_ok=True)
