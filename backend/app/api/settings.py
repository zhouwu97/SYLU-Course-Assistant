"""设置 API（计划 §27 app_settings）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULTS = {
    "interval_min": 8.0,
    "interval_max": 15.0,
    "browser_channel": "edge",
}


class SettingsUpdate(BaseModel):
    interval_min: float | None = Field(None, ge=6, le=120)
    interval_max: float | None = Field(None, ge=6, le=120)
    browser_channel: str | None = None


@router.get("")
async def get_settings(request: Request) -> dict:
    state = request.app.state.app_state
    settings = dict(DEFAULTS)
    for key in DEFAULTS:
        value = await state.db.get_setting(key)
        if value is not None:
            try:
                settings[key] = json.loads(value) if key in ("interval_min", "interval_max") else value
            except (TypeError, json.JSONDecodeError):
                pass
    watcher = request.app.state.watcher
    settings["current"] = {
        "interval_min": watcher.interval_min if watcher else None,
        "interval_max": watcher.interval_max if watcher else None,
        "running": bool(watcher and watcher.running),
    }
    return {"settings": settings}


@router.put("")
async def update_settings(request: Request, body: SettingsUpdate) -> dict:
    state = request.app.state.app_state
    if body.interval_min is not None:
        await state.db.set_setting("interval_min", str(body.interval_min))
    if body.interval_max is not None:
        await state.db.set_setting("interval_max", str(body.interval_max))
    if body.browser_channel is not None:
        await state.db.set_setting("browser_channel", body.browser_channel)
    watcher = request.app.state.watcher
    if watcher is not None:
        if body.interval_min is not None:
            watcher.interval_min = max(6.0, body.interval_min)
        if body.interval_max is not None:
            watcher.interval_max = max(watcher.interval_min, body.interval_max)
    return await get_settings(request)
