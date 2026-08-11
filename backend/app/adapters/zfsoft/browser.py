"""Playwright 浏览器会话管理（计划 §31、§32）。

- 登录态只存在 profile（browser_profile/），不存 Cookie/JSESSIONID
- 首次运行由用户在弹出浏览器中完成学校登录/验证码
- 页面操作必须串行（单浏览器单 page），通过锁保护
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from .endpoints import INDEX_URL, LOGGED_IN_PATH_MARKER


class BrowserSession:
    """管理一个持久化浏览器上下文。"""

    def __init__(
        self,
        profile_dir: str | Path,
        browser_channel: str = "edge",
        headless: bool = False,
        viewport: tuple[int, int] = (1450, 950),
    ):
        self.profile_dir = Path(profile_dir)
        self.browser_channel = browser_channel
        self.headless = headless
        self.viewport = viewport
        self._pw: Playwright | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self._lock = asyncio.Lock()

    # ---- 生命周期 ---------------------------------------------------------

    async def start(self) -> "BrowserSession":
        self._pw = await async_playwright().start()
        launch_kw = dict(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
        )
        try:
            if self.browser_channel == "edge":
                self._context = await self._pw.chromium.launch_persistent_context(channel="msedge", **launch_kw)
            else:
                self._context = await self._pw.chromium.launch_persistent_context(**launch_kw)
        except Exception as e:
            if self.browser_channel == "edge":
                print(f"[browser] Edge 启动失败，回退 Playwright Chromium：{e}")
                self._context = await self._pw.chromium.launch_persistent_context(**launch_kw)
            else:
                raise
        self.page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self.page.set_default_timeout(4500)
        return self

    async def close(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._pw is not None:
            await self._pw.stop()
        self._context = None
        self.page = None
        self._pw = None

    @property
    def running(self) -> bool:
        return self.page is not None

    # ---- 登录状态 ---------------------------------------------------------

    async def goto_index(self) -> None:
        if self.page is None:
            raise RuntimeError("browser not started")
        try:
            await self.page.goto(INDEX_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

    async def is_logged_in(self) -> bool:
        """是否已登录且位于选课模块。"""
        if self.page is None:
            return False
        try:
            text = await self.page.locator("body").inner_text(timeout=2500)
            return LOGGED_IN_PATH_MARKER in self.page.url and "自主选课" in " ".join(text.split())
        except Exception:
            return False

    async def wait_for_login(
        self,
        timeout_s: int = 300,
        on_waiting: Callable[[], Awaitable[None]] | None = None,
    ) -> bool:
        """等待用户在弹出浏览器中完成登录。超时返回 False。"""
        await self.goto_index()
        end = asyncio.get_running_loop().time() + timeout_s
        announced = False
        while asyncio.get_running_loop().time() < end:
            if await self.is_logged_in():
                return True
            if not announced and on_waiting is not None:
                await on_waiting()
                announced = True
            await asyncio.sleep(1.0)
            # 登录完成后若停在首页，尝试回到选课页
            try:
                if self.page is not None and "用户登录" not in await self._body_text() and LOGGED_IN_PATH_MARKER not in self.page.url:
                    await self.goto_index()
            except Exception:
                pass
        return False

    async def _body_text(self) -> str:
        try:
            return " ".join((await self.page.locator("body").inner_text(timeout=2500)).split())
        except Exception:
            return ""
