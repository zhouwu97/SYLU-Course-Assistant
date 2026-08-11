"""决策输出模型（计划 §38）。

每次评估后端都生成一个 Decision：
- requested: 用户请求（课程/活动/教师/时间）
- candidates: 按 tier + score 排序的候选教学班，每个都带 score/reasons/tier/availability
- decision: 程序将执行的动作 + 选中的教学班

前端直接渲染，不允许黑箱（计划 §10）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .course import CourseSection


class DecisionAction(str, Enum):
    NO_ACTION = "NO_ACTION"  # 无满足策略的候选
    NOTIFY = "NOTIFY"  # 模式 A：提醒用户
    WAIT_CONFIRM = "WAIT_CONFIRM"  # 模式 B：等用户确认
    AUTO_ENROLL = "AUTO_ENROLL"  # 模式 C：自动提交


@dataclass
class Candidate:
    section: CourseSection
    tier: int
    score: int
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section.jxbmc,
            "jxb_id": self.section.jxb_id,
            "teacher": self.section.teacher_name,
            "time": "、".join(self._meeting_labels()),
            "availability": self.section.status.value,
            "selected": self.section.selected,
            "capacity": self.section.capacity,
            "tier": self.tier,
            "score": self.score,
            "reasons": list(self.reasons),
        }

    def _meeting_labels(self) -> list[str]:
        nums = ["一", "二", "三", "四", "五", "六", "日"]
        out: list[str] = []
        for m in self.section.meetings:
            name = nums[m.weekday - 1] if 1 <= m.weekday <= 7 else str(m.weekday)
            out.append(f"周{name}{m.start_period}-{m.end_period}节")
        return out or ["时间未知"]


@dataclass
class Decision:
    intent_id: str
    requested: dict[str, Any] = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)
    action: DecisionAction = DecisionAction.NO_ACTION
    selected_section: CourseSection | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "requested": dict(self.requested),
            "candidates": [c.to_dict() for c in self.candidates],
            "decision": {
                "action": self.action.value,
                "section": self.selected_section.jxbmc if self.selected_section else None,
                "jxb_id": self.selected_section.jxb_id if self.selected_section else None,
                "message": self.message,
            },
        }
