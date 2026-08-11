"""选课提交服务（计划 §37、§二十）。

decide() 的 AUTO_ENROLL 结果交给这里执行；EnrollResult 映射为领域状态，
section-level 失败（FULL/CONFLICT）只标记该班，不暂停整门课。
"""
from __future__ import annotations

from app.adapters.zfsoft.enrollment import ZfsoftAdapter
from app.adapters.zfsoft.parser import EnrollOutcome, EnrollResult
from app.domain.course import CourseSection
from app.domain.task import CourseIntent, EnrollmentState

_OUTCOME_TO_STATE = {
    EnrollOutcome.SUCCESS: EnrollmentState.SUCCESS,
    EnrollOutcome.FULL: EnrollmentState.FULL,
    EnrollOutcome.CONFLICT: EnrollmentState.CONFLICT,
    EnrollOutcome.REJECTED: EnrollmentState.REJECTED,
    EnrollOutcome.SESSION_EXPIRED: EnrollmentState.SESSION_EXPIRED,
    EnrollOutcome.NETWORK_ERROR: EnrollmentState.NETWORK_ERROR,
    EnrollOutcome.UNKNOWN: EnrollmentState.UNKNOWN_ERROR,
}


class EnrollmentService:
    """提交执行器。提交永远是 Playwright 页面正常校验链。"""

    def __init__(self, adapter: ZfsoftAdapter):
        self.adapter = adapter

    async def submit(self, intent: CourseIntent, section: CourseSection) -> tuple[EnrollResult, EnrollmentState]:
        result = await self.adapter.enroll(section)
        state = _OUTCOME_TO_STATE.get(result.outcome, EnrollmentState.UNKNOWN_ERROR)
        return result, state

    async def submit_decision(self, intent: CourseIntent, section: CourseSection) -> tuple[EnrollResult, EnrollmentState]:
        """带保护语义的提交：只用于决策引擎选出的教学班。"""
        return await self.submit(intent, section)
