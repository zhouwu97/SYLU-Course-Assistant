"""正方自主选课适配器（计划 §17、§十八）。

业务层只看到 CourseSection / EnrollResult，永远不知道 jxb_ids / xkkz_id /
checkCourse_* 的存在。查询优先走 XHR JSON（页面 JS 发起的列表接口），
提交永远走 Playwright 点击页面真实"选课"按钮（沿用学校 checkCourse_* -> saveCourse 校验链）。
"""
from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from app.domain.course import CourseSection
from app.domain.schedule import Meeting

from .browser import BrowserSession
from .endpoints import LIST_URL_MARKER, SAVE_URL_MARKER
from .parser import (
    EnrollResult,
    EnrollOutcome,
    classify_enroll_result,
    parse_section_from_text,
    parse_sections_from_dom_rows,
    parse_sections_from_items,
)
from .selectors import (
    ACTION_CONTROL_SELECTOR,
    ACTION_LABELS,
    DIALOG_BUTTONS,
    MAX_ANCESTOR_DEPTH,
    QUERY_BUTTON_SELECTORS,
    SEARCH_INPUT_SELECTORS,
    TAB_SELECTOR,
    WITHDRAW_LABELS,
)


class ZfsoftAdapter:
    """正方自主选课模块的完整操作入口。所有方法都假定浏览器已启动。"""

    def __init__(self, session: BrowserSession):
        self.session = session

    @property
    def _page(self) -> Page:
        if self.session.page is None:
            raise RuntimeError("browser session not started")
        return self.session.page

    # ---- 登录 -------------------------------------------------------------

    async def login_status(self) -> bool:
        return await self.session.is_logged_in()

    async def ensure_login(self, timeout_s: int = 300, on_waiting=None) -> bool:
        return await self.session.wait_for_login(timeout_s=timeout_s, on_waiting=on_waiting)

    # ---- 页面操作 ---------------------------------------------------------

    async def click_tab(self, tab: str) -> bool:
        if not tab:
            return True
        page = self._page
        candidates = page.locator(TAB_SELECTOR)
        for i in range(await candidates.count()):
            loc = candidates.nth(i)
            try:
                if not await loc.is_visible():
                    continue
                text = " ".join((await loc.inner_text()).split())
                if text == tab or (tab in text and len(text) <= len(tab) + 8):
                    await loc.click(timeout=2500)
                    await page.wait_for_timeout(700)
                    return True
            except Exception:
                continue
        return False

    async def _find_search_input(self):
        page = self._page
        for sel in SEARCH_INPUT_SELECTORS:
            locs = page.locator(sel)
            for i in range(await locs.count()):
                loc = locs.nth(i)
                try:
                    if await loc.is_visible() and await loc.is_enabled():
                        box = await loc.bounding_box()
                        if box and box["width"] > 120:
                            return loc
                except Exception:
                    continue
        return None

    async def _fill_keyword(self, keyword: str) -> bool:
        inp = await self._find_search_input()
        if inp is None:
            return False
        try:
            if await inp.input_value() != keyword:
                await inp.fill(keyword)
        except Exception:
            pass
        return True

    async def _click_query(self) -> bool:
        page = self._page
        for sel in QUERY_BUTTON_SELECTORS:
            locs = page.locator(sel)
            for i in range(await locs.count()):
                loc = locs.nth(i)
                try:
                    if await loc.is_visible() and await loc.is_enabled():
                        await loc.click(timeout=3000)
                        await page.wait_for_timeout(900)
                        return True
                except Exception:
                    continue
        return False

    async def _dismiss_dialogs(self) -> None:
        page = self._page
        for text in DIALOG_BUTTONS:
            try:
                loc = page.locator(f"button:has-text('{text}'), a:has-text('{text}')")
                if await loc.count() and await loc.first.is_visible():
                    await loc.first.click(timeout=1200)
                    await page.wait_for_timeout(250)
                    return
            except Exception:
                pass

    # ---- 查询：优先 XHR JSON，降级 DOM 行 ----------------------------------

    async def list_sections(
        self, keyword: str, tab: str = "", course_hint: str = ""
    ) -> list[CourseSection]:
        """搜索关键词并返回全部教学班。course_hint 用于 DOM 降级时补课程名。"""
        async with self.session._lock:
            if tab:
                await self.click_tab(tab)
            await self._fill_keyword(keyword)
            sections = await self._query_xhr(keyword, course_hint)
            if not sections:
                sections = await self._query_dom(keyword, course_hint)
            return sections

    async def _query_xhr(self, keyword: str, course_hint: str) -> list[CourseSection]:
        """点击查询并捕获页面 JS 发起的列表接口 JSON。"""
        page = self._page
        try:
            async with page.expect_response(
                lambda r: LIST_URL_MARKER in r.url and "Index" not in r.url and r.request.method == "POST",
                timeout=8000,
            ) as info:
                if not await self._click_query():
                    return []
            resp = await info.value
            data = await resp.json()
        except Exception:
            return []
        items = data.get("items") or data.get("data") or data.get("rows") or []
        if isinstance(items, list):
            return parse_sections_from_items(items, course_hint=course_hint)
        return []

    async def _query_dom(self, keyword: str, course_hint: str) -> list[CourseSection]:
        """降级：直接解析页面表格行。"""
        if not await self._click_query():
            return []
        page = self._page
        rows: list[list[str]] = []
        try:
            trs = page.locator("tr")
            for i in range(await trs.count()):
                cells = await trs.nth(i).locator("td,th").all_inner_texts()
                if cells:
                    rows.append([" ".join(c.split()) for c in cells])
        except Exception:
            pass
        return parse_sections_from_dom_rows(rows, course_hint=course_hint)

    async def get_section_detail(self, section_id: str) -> CourseSection | None:
        """重新查询定位单个教学班。正方没有稳定的明细页，用列表查询替代。"""
        async with self.session._lock:
            page = self._page
            blobs = await self._action_blobs(page, labels=ACTION_LABELS)
            for blob, locator in blobs:
                section = parse_section_from_text(blob)
                if section and (section.jxb_id == section_id or section.jxbmc == section_id):
                    return section
        return None

    async def get_selected_sections(self) -> list[CourseSection]:
        """当前页面中已选（显示"退选"按钮）的教学班。"""
        async with self.session._lock:
            page = self._page
            out: list[CourseSection] = []
            blobs = await self._action_blobs(page, labels=WITHDRAW_LABELS)
            for blob, _loc in blobs:
                section = parse_section_from_text(blob)
                if section:
                    out.append(section)
            return out

    async def get_my_schedule(self) -> list[Meeting]:
        """学生当前课表 = 已选教学班的全部 Meeting。"""
        sections = await self.get_selected_sections()
        return [m for s in sections for m in s.meetings]

    async def _action_blobs(self, page: Page, labels: tuple[str, ...]) -> list[tuple[str, Any]]:
        """收集所有动作按钮的祖先容器文本块。返回 [(blob, locator)]。"""
        locs = page.locator(ACTION_CONTROL_SELECTOR)
        out: list[tuple[str, Any]] = []
        for i in range(await locs.count()):
            loc = locs.nth(i)
            try:
                if not await loc.is_visible() or not await loc.is_enabled():
                    continue
                label = (await loc.inner_text()).strip() if await loc.evaluate("e => e.tagName !== 'INPUT'") else (await loc.get_attribute("value") or "").strip()
                label = " ".join(label.split())
                if label not in labels:
                    continue
                info = await loc.evaluate(
                    """
                    el => {
                        const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
                        const layers = [];
                        let p = el;
                        for (let n = 0; p && n < %d; n++, p = p.parentElement) {
                            const t = norm(p.innerText || p.textContent || '');
                            if (t) layers.push({tag: p.tagName, text: t.slice(0, 2200)});
                        }
                        return {layers};
                    }
                    """ % MAX_ANCESTOR_DEPTH
                )
                for layer in info.get("layers", []):
                    text = layer.get("text", "")
                    if text:
                        out.append((text, loc))
                        break  # 只取最近一层
            except Exception:
                continue
        return out

    # ---- 提交（Playwright 权威执行器，计划 §十八） -------------------------

    async def enroll(self, section: CourseSection) -> EnrollResult:
        """点击教学班对应"选课"按钮，等待服务器最终保存响应。

        优先按 jxb_id 精确匹配按钮祖先文本；DOM 降级产生的 dom:* 用 jxbmc 匹配。
        """
        async with self.session._lock:
            page = self._page
            blobs = await self._action_blobs(page, labels=ACTION_LABELS)
            target_loc = None
            for blob, loc in blobs:
                if section.jxb_id and not section.jxb_id.startswith("dom:"):
                    if section.jxb_id in blob:
                        target_loc = loc
                        break
                elif section.jxbmc and section.jxbmc in blob:
                    target_loc = loc
                    break
            if target_loc is None:
                return EnrollResult(EnrollOutcome.REJECTED, f"页面未找到教学班 {section.jxbmc} 的选课按钮")

            try:
                async with page.expect_response(
                    lambda r: SAVE_URL_MARKER in r.url and r.request.method == "POST",
                    timeout=12000,
                ) as info:
                    await target_loc.click(timeout=4000)
                resp = await info.value
                result = classify_enroll_result(await resp.json())
                result.endpoint = resp.url
                return result
            except PlaywrightTimeoutError:
                # 校验链在 saveCourse 前终止；读取页面提示
                await page.wait_for_timeout(900)
                try:
                    page_text = await page.locator("body").inner_text(timeout=2500)
                except Exception:
                    page_text = ""
                return classify_enroll_result({}, page_text=page_text)

    async def withdraw(self, section: CourseSection) -> EnrollResult:
        """退选（已选教学班显示退选按钮时）。"""
        async with self.session._lock:
            page = self._page
            blobs = await self._action_blobs(page, labels=WITHDRAW_LABELS)
            target_loc = None
            for blob, loc in blobs:
                if section.jxb_id and not section.jxb_id.startswith("dom:"):
                    if section.jxb_id in blob:
                        target_loc = loc
                        break
                elif section.jxbmc and section.jxbmc in blob:
                    target_loc = loc
                    break
            if target_loc is None:
                return EnrollResult(EnrollOutcome.REJECTED, f"页面未找到教学班 {section.jxbmc} 的退选按钮")
            try:
                async with page.expect_response(
                    lambda r: SAVE_URL_MARKER in r.url and r.request.method == "POST",
                    timeout=12000,
                ) as info:
                    await target_loc.click(timeout=4000)
                resp = await info.value
                result = classify_enroll_result(await resp.json())
                result.endpoint = resp.url
                return result
            except PlaywrightTimeoutError:
                await page.wait_for_timeout(900)
                return EnrollResult(EnrollOutcome.UNKNOWN, "未捕获到退选保存响应")
