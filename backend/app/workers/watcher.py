"""候补监测引擎（计划 §19、§21、§29、§30、§37）。

- 按课程关键词分组查询，同一关键词一次查询（计划 §29）
- 默认间隔 8~15 秒，最低 6 秒；异常指数退避 10s/20s/40s/60s（计划 §30）
- 每个 tick：查询一次当前课表 -> 分组查询教学班 -> 逐意图 decide()
- 只有 decision.action == AUTO_ENROLL 才提交（计划 §37）
- section-level 失败（FULL/CONFLICT）标记该班，不暂停整门课（计划 §20）
- SESSION_EXPIRED 暂停整个引擎等待重新登录（计划 §31）
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from app.app_state import AppState
from app.domain.course import CourseSection
from app.domain.task import (
    COURSE_LEVEL_STATES,
    SECTION_LEVEL_STATES,
    EnrollmentState,
)
from app.services.ranking import decide
from app.api.websocket import manager as ws_manager

DEFAULT_INTERVAL = (8.0, 15.0)
MIN_INTERVAL = 6.0
MAX_BACKOFF = 60.0


class Watcher:
    def __init__(
        self,
        state: AppState,
        interval_min: float = DEFAULT_INTERVAL[0],
        interval_max: float = DEFAULT_INTERVAL[1],
    ):
        if interval_min < MIN_INTERVAL:
            interval_min = MIN_INTERVAL
        if interval_max < interval_min:
            interval_max = interval_min
        self.state = state
        self.interval_min = interval_min
        self.interval_max = interval_max
        self.interval_seconds: float | None = None
        self.last_check_at: str | None = None
        self.running = False
        self.paused = False
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._failed_sections: dict[str, set[str]] = {}  # intent_id -> {jxb_id}
        self._pending_confirmations: dict[str, CourseSection] = {}  # intent_id -> section
        self._backoff = 0.0

    # ---- 事件日志 + 实时推送 ----------------------------------------------

    async def _log(self, intent_id: str, message: str, level: str = "info") -> None:
        event = await self.state.db.add_event(intent_id, message, level)
        await ws_manager.broadcast(event.to_dict())

    # ---- 生命周期 ---------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None:
            return
        self.running = True
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="sylu-watcher")

    async def stop(self) -> None:
        self.running = False
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False
        self._backoff = 0.0

    def reset_failed(self, intent_id: str) -> None:
        self._failed_sections.pop(intent_id, None)

    def seconds_until_next(self) -> float | None:
        if not self.running or self.interval_seconds is None:
            return None
        return round(self.interval_seconds, 1)

    # ---- 主循环 -----------------------------------------------------------

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.paused:
                    await self._tick()
                self._backoff = 0.0
                delay = random.uniform(self.interval_min, self.interval_max)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.state._last_watcher_error = f"{type(e).__name__}: {e}"
                # 指数退避（计划 §30）：10s 20s 40s 60s
                self._backoff = min(MAX_BACKOFF, (self._backoff * 2) if self._backoff else 10.0)
                delay = self._backoff
            self.interval_seconds = delay
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                raise

    async def _tick(self) -> None:
        db = self.state.db
        self.last_check_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        intents = [i for i in await db.list_intents() if i.state in _ACTIVE_STATES]
        if not intents:
            return

        adapter = await self.state.get_adapter()
        my_schedule = await adapter.get_my_schedule()

        from app.services.course_discovery import group_queries_by_keyword

        for keyword, group in group_queries_by_keyword(intents).items():
            sections = await adapter.list_sections(keyword, tab=_tab_for(group[0]))
            await self._log("", f"更新教学班：{keyword}（{len(sections)} 个）", level="info")
            for intent in group:
                await self._evaluate(intent, sections, my_schedule)

    async def _evaluate(self, intent, sections, my_schedule) -> None:
        db = self.state.db
        failed = self._failed_sections.get(intent.intent_id, set())
        candidates = [s for s in sections if s.jxb_id not in failed]
        decision = decide(candidates, intent, my_schedule)

        if decision.action.value == "NO_ACTION":
            await self._log(
                intent.intent_id,
                f"{decision.requested['activity']}：{decision.message}",
                level="info",
            )
            return

        if decision.action.value == "NOTIFY":
            await self._log(
                intent.intent_id,
                f"[提醒] {decision.message}",
                level="success",
            )
            intent.state = EnrollmentState.CANDIDATE_FOUND
            await db.upsert_intent(intent)
            return

        if decision.action.value == "WAIT_CONFIRM":
            # 模式 B：等用户确认（计划 §11）
            self._pending_confirmations[intent.intent_id] = decision.selected_section
            await self._log(
                intent.intent_id,
                f"[待确认] {decision.message}",
                level="warn",
            )
            intent.state = EnrollmentState.WAITING_CONFIRMATION
            await db.upsert_intent(intent)
            return

        # AUTO_ENROLL（计划 §37：决策引擎选出的班才能提交）
        section = decision.selected_section
        await self._log(
            intent.intent_id,
            f"[提交] 自动选择 {section.jxbmc}（{section.availability_text}）",
            level="warn",
        )
        result, state = await (await self.state.enrollment()).submit_decision(intent, section)
        await self._log(intent.intent_id, f"[结果] {result.outcome.value}: {result.message}",
                        level="success" if result.ok else "error")

        if result.is_section_level:
            # 单班失败：标记不可用，重新排序找下一个（计划 §20）
            self._failed_sections.setdefault(intent.intent_id, set()).add(section.jxb_id)
            intent.state = EnrollmentState.WAITING
            await self._log(
                intent.intent_id,
                f"{section.jxbmc} 标记不可用（{result.outcome.value}），继续候补",
                level="warn",
            )
        elif state in COURSE_LEVEL_STATES:
            intent.state = state
            if state == EnrollmentState.SESSION_EXPIRED:
                self.pause()
                await self._log(
                    intent.intent_id,
                    "登录已失效，自动候补已暂停，请重新登录",
                    level="error",
                )
        else:
            intent.state = state
        intent.updated_at = db_util_now()
        await db.upsert_intent(intent)

    # ---- 模式 B：用户确认 / 放弃 ------------------------------------------

    async def submit_pending(self, intent) -> CourseSection | None:
        """用户确认后提交待确认教学班。返回提交的教学班，无待确认返回 None。"""
        section = self._pending_confirmations.pop(intent.intent_id, None)
        if section is None:
            return None
        result, state = await (await self.state.enrollment()).submit_decision(intent, section)
        await self._log(intent.intent_id, f"[确认] 提交 {section.jxbmc} -> {result.outcome.value}: {result.message}",
                        level="success" if result.ok else "error")
        if result.is_section_level:
            self._failed_sections.setdefault(intent.intent_id, set()).add(section.jxb_id)
            intent.state = EnrollmentState.WAITING
        elif state in COURSE_LEVEL_STATES:
            intent.state = state
        else:
            intent.state = state
        intent.updated_at = db_util_now()
        await self.state.db.upsert_intent(intent)
        return section

    def decline_pending(self, intent_id: str) -> bool:
        """用户放弃替代班，继续等首选。"""
        if intent_id in self._pending_confirmations:
            del self._pending_confirmations[intent_id]
            return True
        return False


def _tab_for(intent) -> str:
    return {"main": "主修课程", "general": "通识选修课", "sport": "体育分项"}.get(intent.category, "")


def db_util_now() -> str:
    from app.domain.task import utc_now

    return utc_now()


_ACTIVE_STATES = {
    EnrollmentState.WAITING,
    EnrollmentState.DISCOVERING,
    EnrollmentState.CANDIDATE_FOUND,
    EnrollmentState.WAITING_CONFIRMATION,
    EnrollmentState.FULL,
    EnrollmentState.CONFLICT,
    EnrollmentState.REJECTED,
}
