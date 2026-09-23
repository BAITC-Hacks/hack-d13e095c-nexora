import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.db.base import Base
from app.main import create_app


@pytest.fixture
async def env(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    schema = "test_" + uuid4().hex
    admin = None
    if url:
        # Each test gets an isolated schema, never drop user tables/databases.
        admin = create_async_engine(url)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            url, poolclass=NullPool, connect_args={"server_settings": {"search_path": schema}}
        )
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")

        @event.listens_for(engine.sync_engine, "connect")
        def enable_fk(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    font = Path(
        os.getenv(
            "PDF_FONT_PATH",
            "C:/Windows/Fonts/arial.ttf"
            if os.name == "nt"
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
    )
    bold = Path(
        os.getenv(
            "PDF_BOLD_FONT_PATH",
            "C:/Windows/Fonts/arialbd.ttf"
            if os.name == "nt"
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )
    )
    settings = Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        database_url=str(engine.url),
        max_upload_mb=1,
        pdf_font_path=font,
        pdf_bold_font_path=bold,
    )
    app = create_app(settings, factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield {
            "client": client,
            "factory": factory,
            "settings": settings,
            "app": app,
            "postgres": bool(url),
        }
    await engine.dispose()
    if admin:
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()
