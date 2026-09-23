import json
import subprocess
import wave
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.services.audio_service import AudioService
from app.utils.errors import PipelineError


@pytest.mark.parametrize(
    "extension,codec",
    [
        ("wav", "pcm_s16le"),
        ("mp3", "libmp3lame"),
        ("m4a", "aac"),
        ("mp4", "aac"),
        ("webm", "libopus"),
    ],
)
def test_real_ffmpeg_normalizes_supported_containers(tmp_path, extension, codec):
    import imageio_ffmpeg

    binary = imageio_ffmpeg.get_ffmpeg_exe()
    source = tmp_path / f"original.{extension}"
    subprocess.run(
        [
            binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-c:a",
            codec,
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    service = AudioService(Settings(_env_file=None, ffmpeg_binary=binary))
    actual_run = service._run

    # imageio bundles ffmpeg but not ffprobe; probe error paths are covered separately above.
    def run(args, timeout):
        if args[0] == "ffprobe":
            return json.dumps({"streams": [{"codec_type": "audio"}], "format": {"duration": "1"}})
        return actual_run(args, timeout)

    service._run = run
    destination = tmp_path / "normalized.wav"
    duration = service.extract(source, destination)
    with wave.open(str(destination), "rb") as result:
        assert (result.getnchannels(), result.getframerate(), result.getsampwidth()) == (
            1,
            16000,
            2,
        )
    assert 0.9 <= duration <= 1.2


def test_ffmpeg_arguments_safe_and_pcm_output(monkeypatch, tmp_path):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if "ffprobe" in args[0]:
            return Mock(
                returncode=0,
                stdout=json.dumps(
                    {"streams": [{"codec_type": "audio"}], "format": {"duration": "1"}}
                ),
            )
        with wave.open(args[-1], "wb") as output:
            output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            output.writeframes(b"\x00\x00" * 16000)
        return Mock(returncode=0, stdout="")

    monkeypatch.setattr(subprocess, "run", run)
    destination = tmp_path / "meeting.wav"
    result = AudioService(Settings(_env_file=None)).extract(tmp_path / "a;evil.mp4", destination)
    assert result == 1 and destination.is_file()
    args, kwargs = calls[-1]
    assert args[args.index("-ar") + 1] == "16000"
    assert args[args.index("-ac") + 1] == "1"
    assert "pcm_s16le" in args and not kwargs.get("shell", False)
    assert str(tmp_path / "a;evil.mp4") in args


@pytest.mark.parametrize(
    "case,code",
    [
        ("no_audio", "NO_AUDIO_STREAM"),
        ("too_long", "AUDIO_DURATION_LIMIT"),
        ("timeout", "MEDIA_PROCESSING_TIMEOUT"),
        ("invalid", "INVALID_OR_UNSUPPORTED_MEDIA"),
    ],
)
def test_media_failures(monkeypatch, tmp_path, case, code):
    def run(args, **kwargs):
        if case == "timeout":
            raise subprocess.TimeoutExpired(args, 1)
        if case == "invalid":
            return Mock(returncode=1)
        return Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [] if case == "no_audio" else [{"codec_type": "audio"}],
                    "format": {"duration": "999999"},
                }
            ),
        )

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(PipelineError, match=code):
        AudioService(Settings(_env_file=None)).extract(Path("input.mp4"), tmp_path / "meeting.wav")
