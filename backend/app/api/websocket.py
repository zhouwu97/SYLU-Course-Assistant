"""WebSocket 实时推送（计划 §21、§33）。

后端事件（人数变化/推荐变化/任务状态/日志）通过 /api/ws 推给前端。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._recent: list[dict[str, Any]] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        # 连接后先补发最近事件，避免刷新丢日志
        for event in self._recent[-50:]:
            try:
                await ws.send_text(json.dumps(event, ensure_ascii=False))
            except Exception:
                break

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        event = {"type": "event", **event}
        self._recent.append(event)
        if len(self._recent) > 200:
            self._recent = self._recent[-200:]
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(json.dumps(event, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def clients(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


@router.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # 心跳/忽略前端消息
            await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
