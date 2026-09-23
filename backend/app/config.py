from functools import lru_cache
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def is_local_address(value: str) -> bool:
    address = ip_address(value)
    return address.is_loopback or any(
        address in ip_network(network)
        for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://meetings:meetings@localhost:5432/meetings"
    storage_dir: Path = Path("storage")
    max_upload_mb: int = Field(default=512, ge=1, le=10240)
    max_audio_seconds: int = Field(default=14400, ge=1)
    ffmpeg_timeout_seconds: int = Field(default=1800, ge=1)
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    ai_device: Literal["cpu", "cuda"] = "cpu"
    whisper_model: str = "large-v3"
    whisper_model_dir: Path = Path("models/whisper-large-v3")
    whisper_compute_type: str = "int8"
    whisper_cpu_threads: int = Field(default=4, ge=1)
    diarization_model_dir: Path = Path("models/pyannote-community-1")
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: int = Field(default=600, ge=1)
    llm_chunk_chars: int = Field(default=6000, ge=1000, le=20000)
    llm_context_tokens: int = Field(default=32768, ge=8192)
    meeting_timezone: str = "Asia/Almaty"
    worker_poll_seconds: float = Field(default=2, ge=0.1)
    job_lease_seconds: int = Field(default=120, ge=30)
    job_max_attempts: int = Field(default=3, ge=1)
    api_key: str | None = None
    conference_access_key: str | None = None
    conference_max_peers: int = Field(default=8, ge=2, le=12)
    rtc_ice_servers: list[dict] = []
    speech_url: str = "http://speech:8001"
    speech_api_key: str = ""
    speech_timeout_seconds: int = Field(default=120, ge=5, le=600)
    live_analysis_interval: int = Field(default=30, ge=10, le=300)
    memory_access_key: str | None = None
    ollama_keep_alive: str = "5m"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    pdf_font_path: Path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    pdf_bold_font_path: Path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

    @field_validator("meeting_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("ollama_url")
    @classmethod
    def local_ollama_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("OLLAMA_URL must be an HTTP origin of a local Ollama server")
        if parsed.hostname not in {"localhost", "ollama", "host.docker.internal"}:
            try:
                valid = is_local_address(parsed.hostname)
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(
                    "Ollama must use localhost, ollama, host.docker.internal or a private IP"
                )
        return value.rstrip("/")

    @field_validator("ollama_model")
    @classmethod
    def no_cloud_model(cls, value: str) -> str:
        if "cloud" in value.lower() or "://" in value:
            raise ValueError("Cloud models are prohibited")
        return value

    @model_validator(mode="after")
    def context_fits(self):
        # Conservative upper bound: UTF-8 bytes can exceed the character count.
        if self.llm_chunk_chars * 3 + 10000 > self.llm_context_tokens:
            raise ValueError("Increase LLM_CONTEXT_TOKENS or reduce LLM_CHUNK_CHARS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
