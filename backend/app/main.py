"""SYLU Course Assistant - FastAPI 入口（计划 §33）。

本地运行：uvicorn app.main:app --app-dir backend --port 8765
浏览器访问 http://localhost:8765
"""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, courses, plans, settings, tasks, websocket
from .app_state import AppState
from .workers.watcher import Watcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("sylu")


class _SensitiveFormatter(logging.Formatter):
    """开发日志（计划 §23）：记录 endpoint/response/selector/exception，
    但 Cookie/token 等敏感值一律打码。"""

    _SENSITIVE = re.compile(
        r"(?i)(jsessionid|cookie|token|authorization)\s*[=:]\s*[^\s;\"']+"
    )

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        record.msg = self._SENSITIVE.sub(r"\1=***", msg)
        return super().format(record)


def _setup_debug_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_SensitiveFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(handler)


_ROOT = Path(__file__).resolve().parent.parent.parent


def create_app(state: AppState | None = None) -> FastAPI:
    state = state or AppState(
        db_path=_ROOT / "data" / "sylu.db",
        profile_dir=_ROOT / "browser_profile",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _setup_debug_log(_ROOT / "logs" / "debug.log")
        await state.init()
        # 从设置读取监测间隔（计划 §30）
        try:
            interval_min = float(await state.db.get_setting("interval_min") or 8.0)
            interval_max = float(await state.db.get_setting("interval_max") or 15.0)
        except (TypeError, ValueError):
            interval_min, interval_max = 8.0, 15.0
        watcher = Watcher(state, interval_min=interval_min, interval_max=interval_max)
        app.state.watcher = watcher
        await watcher.start()
        logger.info("SYLU Course Assistant backend started (http://localhost:8765)")
        try:
            yield
        finally:
            await watcher.stop()
            await state.close()

    app = FastAPI(
        title="SYLU Course Assistant",
        version="3.0.0",
        lifespan=lifespan,
    )
    app.state.app_state = state
    app.state.watcher = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8765"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(courses.router)
    app.include_router(plans.router)
    app.include_router(tasks.router)
    app.include_router(settings.router)
    app.include_router(websocket.router)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "version": "3.0.0"}

    # 前端构建产物（Phase 6 之后存在）；放在所有 API 路由之后挂载，避免遮蔽 /api
    dist = _ROOT / "frontend" / "dist"
    if dist.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    return app


app = create_app()
