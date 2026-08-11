"""应用全局状态：DB + 浏览器适配器 + 各服务。

测试时通过 create_app(state=...) 注入 FakeAdapter。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.zfsoft.browser import BrowserSession
from app.adapters.zfsoft.enrollment import ZfsoftAdapter
from app.services.course_discovery import CourseDiscoveryService
from app.services.enrollment_service import EnrollmentService
from app.storage.database import Database

CATEGORIES = [
    {"id": "main", "label": "主修课程"},
    {"id": "general", "label": "通识选修课"},
    {"id": "sport", "label": "体育分项"},
]


class AppState:
    def __init__(
        self,
        db_path: str | Path = "data/sylu.db",
        adapter: ZfsoftAdapter | None = None,
        browser_channel: str = "edge",
        profile_dir: str | Path = "browser_profile",
    ):
        self.db = Database(db_path)
        self._adapter = adapter
        self.browser_channel = browser_channel
        self.profile_dir = Path(profile_dir)
        self._session: BrowserSession | None = None

    async def init(self) -> None:
        await self.db.init()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
        await self.db.close()

    # ---- 适配器（懒启动浏览器） -------------------------------------------

    async def get_adapter(self) -> ZfsoftAdapter:
        if self._adapter is not None:
            return self._adapter
        if self._session is None or not self._session.running:
            self._session = await BrowserSession(
                profile_dir=self.profile_dir,
                browser_channel=self.browser_channel,
            ).start()
        if self._adapter is None:
            self._adapter = ZfsoftAdapter(self._session)
        return self._adapter

    async def login_status(self) -> bool:
        if self._adapter is None and (self._session is None or not self._session.running):
            return False
        return await (await self.get_adapter()).login_status()

    async def open_login(self, wait_timeout_s: int = 300) -> bool:
        """打开浏览器等待登录。首次运行用户需要在弹出的浏览器里完成学校登录。"""
        adapter = await self.get_adapter()
        return await adapter.ensure_login(timeout_s=wait_timeout_s)

    # ---- 服务 -------------------------------------------------------------

    async def discovery(self) -> CourseDiscoveryService:
        return CourseDiscoveryService(await self.get_adapter())

    async def enrollment(self) -> EnrollmentService:
        return EnrollmentService(await self.get_adapter())
