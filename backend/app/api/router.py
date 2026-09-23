from fastapi import APIRouter, Depends

from app.api import exports, health, meetings, participants, tasks
from app.api.deps import require_api_key

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
for module in (health, meetings, participants, tasks, exports):
    router.include_router(module.router)
