"""SYLU Course Assistant - FastAPI 入口（计划 §33）。

本地运行：uvicorn app.main:app --app-dir backend --port 8765
浏览器访问 http://localhost:8765
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, courses, plans, tasks
from .app_state import AppState
from .workers.watcher import Watcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("sylu")

_ROOT = Path(__file__).resolve().parent.parent.parent


def create_app(state: AppState | None = None) -> FastAPI:
    state = state or AppState(
        db_path=_ROOT / "data" / "sylu.db",
        profile_dir=_ROOT / "browser_profile",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await state.init()
        watcher = Watcher(state)
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

    # 前端构建产物（Phase 6 之后存在）
    dist = _ROOT / "frontend" / "dist"
    if dist.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "version": "3.0.0"}

    return app


app = create_app()
