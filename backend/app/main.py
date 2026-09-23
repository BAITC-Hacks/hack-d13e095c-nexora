from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers

from app.api.router import router
from app.api.conferences import router as conference_router
from app.services.conference_service import ConferenceHub
from app.config import Settings, get_settings
from app.db.session import create_database


class UploadLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                    scope, receive, send
                )
            if length < 0 or length > self.max_bytes:
                return await JSONResponse({"detail": "Request body too large"}, status_code=413)(
                    scope, receive, send
                )
        consumed = 0

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > self.max_bytes:
                raise HTTPException(413, "Request body too large")
            return message

        await self.app(scope, limited_receive, send)


def create_app(settings: Settings | None = None, session_factory=None) -> FastAPI:
    settings = settings or get_settings()
    engine = None
    if session_factory is None:
        engine, session_factory = create_database(settings)

    @asynccontextmanager
    async def lifespan(app):
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        yield
        if engine:
            await engine.dispose()

    app = FastAPI(
        title="Local Meeting Minutes",
        version="1.0.0",
        lifespan=lifespan,
        description="Локальная обработка RU/KK совещаний. Аудио и текст не отправляются во внешние AI API.",
    )
    app.state.settings, app.state.session_factory = settings, session_factory
    app.state.conference_hub = ConferenceHub()
    app.add_middleware(
        UploadLimitMiddleware, max_bytes=settings.max_upload_mb * 1024 * 1024 + 65536
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    app.include_router(router)
    app.include_router(conference_router)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse(
            status_code=409,
            content={"detail": "Concurrent update or invalid relation; retry the operation"},
        )

    return app


app = create_app()
