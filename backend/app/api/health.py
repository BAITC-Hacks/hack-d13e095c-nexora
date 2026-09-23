import shutil

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from app.api.deps import Config, Session
from app.services.llm_service import LLMService
from app.utils.errors import PipelineError

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request):
    try:
        async with request.app.state.session_factory() as session:
            await session.execute(text("SELECT version_num FROM alembic_version"))
    except Exception as exc:
        raise HTTPException(503, "Database or migrations unavailable") from exc
    return {"status": "ready"}


@router.get("/health/models")
async def models(settings: Config, session: Session):
    import httpx

    checks = {
        "whisper": (settings.whisper_model_dir / "model.bin").is_file(),
        "diarization": (settings.diarization_model_dir / "config.yaml").is_file(),
        "ffmpeg": shutil.which(settings.ffmpeg_binary) is not None,
        "ollama_model": False,
    }
    try:
        origin, host = await LLMService(settings)._local_origin()
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
            response = await client.post(
                origin + "/api/show", headers={"Host": host}, json={"model": settings.ollama_model}
            )
            checks["ollama_model"] = response.status_code == 200 and not response.json().get(
                "remote_host"
            )
    except (PipelineError, httpx.HTTPError, ValueError):
        pass
    if not all(checks.values()):
        raise HTTPException(503, checks)
    return checks
