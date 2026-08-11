"""任务 API（计划 §22、§23、§33）：任务列表 / 事件日志 / 引擎状态。"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/status")
async def engine_status(request: Request) -> dict:
    """自动化引擎总览：登录状态、活动任务、最后/下次检查时间。"""
    state = request.app.state.app_state
    intents = await state.db.list_intents()
    watcher = request.app.state.watcher
    return {
        "loggedIn": await state.login_status(),
        "engineRunning": bool(watcher and watcher.running),
        "enginePaused": bool(watcher and watcher.paused),
        "activeTasks": sum(1 for i in intents if i.state.value not in ("IDLE", "SUCCESS", "PAUSED")),
        "lastCheckAt": watcher.last_check_at if watcher else None,
        "nextCheckInSeconds": watcher.seconds_until_next() if watcher else None,
        "intervalSeconds": watcher.interval_seconds if watcher else None,
    }


@router.get("/tasks")
async def list_tasks(request: Request) -> dict:
    state = request.app.state.app_state
    intents = await state.db.list_intents()
    return {"tasks": [i.to_dict() for i in intents]}


@router.get("/events")
async def list_events(
    request: Request,
    intent_id: str | None = None,
    limit: int = Query(100, le=500),
) -> dict:
    state = request.app.state.app_state
    events = await state.db.list_events(intent_id=intent_id, limit=limit)
    return {"events": [e.to_dict() for e in events]}


@router.post("/engine/pause")
async def engine_pause(request: Request) -> dict:
    """暂停全部自动候补（计划 §22）。"""
    watcher = request.app.state.watcher
    if watcher is not None:
        watcher.pause()
    state = request.app.state.app_state
    from app.api.websocket import manager as ws_manager

    event = await state.db.add_event("", "全部任务已暂停", level="warn")
    await ws_manager.broadcast(event.to_dict())
    return {"paused": True}


@router.post("/engine/resume")
async def engine_resume(request: Request) -> dict:
    watcher = request.app.state.watcher
    if watcher is not None:
        watcher.resume()
    state = request.app.state.app_state
    from app.api.websocket import manager as ws_manager

    event = await state.db.add_event("", "全部任务已恢复", level="success")
    await ws_manager.broadcast(event.to_dict())
    return {"paused": False}
