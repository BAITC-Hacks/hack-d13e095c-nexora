"""Self-hosted multilingual ASR; never downloads a model while processing audio."""

import asyncio
import io
import os
import secrets
import wave
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

model = None
load_error = None
lock = asyncio.Lock()


def load_model():
    global model, load_error
    try:
        from faster_whisper import WhisperModel

        model_dir = Path(os.getenv("SPEECH_MODEL_DIR", "/models/whisper"))
        if not (model_dir / "model.bin").is_file():
            raise FileNotFoundError("Run speech-bootstrap first")
        model = WhisperModel(
            str(model_dir),
            local_files_only=True,
            device=os.getenv("AI_DEVICE", "cpu"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            cpu_threads=int(os.getenv("WHISPER_CPU_THREADS", "4")),
        )
    except Exception as exc:
        load_error = type(exc).__name__


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(load_model)
    yield


app = FastAPI(lifespan=lifespan)


def authenticate(key):
    expected = os.getenv("SPEECH_API_KEY", "")
    if expected and not secrets.compare_digest(key or "", expected):
        raise HTTPException(401, "Invalid speech key")


@app.get("/health")
async def health(x_speech_key: str | None = Header(default=None)):
    authenticate(x_speech_key)
    return JSONResponse(
        {"ready": model is not None, "error": load_error}, status_code=200 if model else 503
    )


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(), x_speech_key: str | None = Header(default=None)):
    authenticate(x_speech_key)
    if model is None:
        raise HTTPException(503, "Speech model not ready")
    content = await file.read(512_001)
    if len(content) > 512_000:
        raise HTTPException(413, "Audio chunk too large")
    try:
        with wave.open(io.BytesIO(content), "rb") as wav:
            if (
                wav.getnchannels() != 1
                or wav.getsampwidth() != 2
                or wav.getframerate() != 16000
                or not 0.05 <= wav.getnframes() / 16000 <= 15
            ):
                raise ValueError()
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(422, "Expected 16kHz mono WAV") from None

    def infer():
        segments, info = model.transcribe(
            io.BytesIO(content),
            language=None,
            multilingual=True,
            task="transcribe",
            beam_size=3,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt="Совещание. Жиналыс. Русская и казахская речь, имена, поручения и сроки.",
        )
        return {
            "language": info.language,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text.strip()}
                for s in segments
                if s.text.strip() and s.end > s.start
            ],
        }

    async with lock:
        return await asyncio.to_thread(infer)
