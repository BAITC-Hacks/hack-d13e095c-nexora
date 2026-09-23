import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings


def settings_from_request(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request):
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def require_api_key(request: Request, x_api_key: str | None = Header(default=None)):
    expected = request.app.state.settings.api_key
    if expected and (not x_api_key or not secrets.compare_digest(expected, x_api_key)):
        raise HTTPException(401, "Invalid or missing X-API-Key")


Session = Annotated[AsyncSession, Depends(get_session, scope="function")]
Config = Annotated[Settings, Depends(settings_from_request)]
