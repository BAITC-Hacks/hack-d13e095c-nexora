import asyncio
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, is_local_address
from app.utils.errors import PipelineError


class LiveSpeechSegment(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(max_length=4000)


class LiveSpeechResult(BaseModel):
    segments: list[LiveSpeechSegment] = Field(max_length=100)
    language: str


class SpeechClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def origin(self):
        parsed = urlsplit(self.settings.speech_url)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise PipelineError("SPEECH_URL_INVALID")
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo, parsed.hostname, parsed.port or 8001, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise PipelineError("SPEECH_UNAVAILABLE") from exc
        if not addresses or any(not is_local_address(a[4][0]) for a in addresses):
            raise PipelineError("SPEECH_NONLOCAL_ADDRESS_BLOCKED")
        ip = addresses[0][4][0]
        host = f"[{ip}]" if ":" in ip else ip
        return f"http://{host}:{parsed.port or 8001}", {
            "Host": parsed.netloc,
            "X-Speech-Key": self.settings.speech_api_key,
        }

    async def ready(self):
        origin, headers = await self.origin()
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
            response = await client.get(origin + "/health", headers=headers)
            response.raise_for_status()
            return bool(response.json()["ready"])

    async def transcribe(self, path: Path):
        origin, headers = await self.origin()
        async with httpx.AsyncClient(
            timeout=self.settings.speech_timeout_seconds, trust_env=False, follow_redirects=False
        ) as client:
            content = await asyncio.to_thread(path.read_bytes)
            response = await client.post(
                origin + "/transcribe",
                headers=headers,
                files={"file": ("chunk.wav", content, "audio/wav")},
            )
            response.raise_for_status()
            return LiveSpeechResult.model_validate(response.json())
