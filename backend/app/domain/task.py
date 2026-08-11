"""任务 / 状态机领域模型（计划 §13、§十九、§二十）。

状态分层（计划 §20）：
- section-level 失败（FULL / CONFLICT / REJECTED）：只标记该教学班不可用，继续找其他候选
- course-level 失败（SESSION_EXPIRED / 资格不允许）：暂停整个 CourseIntent
- system-level 失败（NETWORK_ERROR / UNKNOWN_ERROR）：任务级重试/退避
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .preference import CoursePreference
from .schedule import Meeting


class EnrollmentState(str, Enum):
    IDLE = "IDLE"
    DISCOVERING = "DISCOVERING"
    WAITING = "WAITING"
    CANDIDATE_FOUND = "CANDIDATE_FOUND"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    SUBMITTING = "SUBMITTING"
    SUCCESS = "SUCCESS"
    # section-level：继续找其他候选，不停整门课
    FULL = "FULL"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"
    # course/system-level：暂停任务
    SESSION_EXPIRED = "SESSION_EXPIRED"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    PAUSED = "PAUSED"


# section-level 状态：单个教学班失败后应重新排序其他候选，而非停掉任务
SECTION_LEVEL_STATES = {
    EnrollmentState.FULL,
    EnrollmentState.CONFLICT,
    EnrollmentState.REJECTED,
}

# 任务级暂停状态：需要人工介入
COURSE_LEVEL_STATES = {
    EnrollmentState.SESSION_EXPIRED,
    EnrollmentState.NETWORK_ERROR,
    EnrollmentState.UNKNOWN_ERROR,
    EnrollmentState.PAUSED,
}

TERMINAL_STATES = {EnrollmentState.SUCCESS, EnrollmentState.PAUSED}


class AutomationMode(str, Enum):
    """自动执行模式（计划 §11）。"""

    NOTIFY = "notify"  # 模式 A：仅提醒，用户自己点
    CONFIRM = "confirm"  # 模式 B：确认后选（默认）
    AUTO = "auto"  # 模式 C：全自动


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class CourseIntent:
    """一门课程的选课意图 + 偏好规则（计划 §13）。"""

    intent_id: str
    course_id: str = ""  # kch_id
    course_name: str = ""
    category: str = ""  # main / general / sport
    keyword: str = ""  # 搜索关键词，如 "羽毛球"
    priority: int = 100  # 越小越优先（计划 §14 课程间优先级）
    mode: AutomationMode = AutomationMode.CONFIRM
    state: EnrollmentState = EnrollmentState.IDLE
    preference: CoursePreference = field(default_factory=CoursePreference)
    existing_schedule: list[Meeting] = field(default_factory=list)  # 学生当前课表
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "course_id": self.course_id,
            "course_name": self.course_name,
            "category": self.category,
            "keyword": self.keyword,
            "priority": self.priority,
            "mode": self.mode.value,
            "state": self.state.value,
            "preference": self.preference.to_dict(),
            "existing_schedule": [
                {
                    "weekday": m.weekday,
                    "start_period": m.start_period,
                    "end_period": m.end_period,
                    "weeks": sorted(m.weeks),
                    "place": m.place,
                }
                for m in self.existing_schedule
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CourseIntent":
        schedule_raw = d.get("existing_schedule") or []
        meetings: list[Meeting] = []
        for m in schedule_raw:
            meetings.append(
                Meeting(
                    weekday=int(m["weekday"]),
                    start_period=int(m["start_period"]),
                    end_period=int(m["end_period"]),
                    weeks=frozenset(m.get("weeks") or range(1, 17)),
                    place=str(m.get("place") or ""),
                )
            )
        return cls(
            intent_id=str(d["intent_id"]),
            course_id=str(d.get("course_id") or ""),
            course_name=str(d.get("course_name") or ""),
            category=str(d.get("category") or ""),
            keyword=str(d.get("keyword") or ""),
            priority=int(d.get("priority", 100)),
            mode=AutomationMode(d.get("mode", AutomationMode.CONFIRM.value)),
            state=EnrollmentState(d.get("state", EnrollmentState.IDLE.value)),
            preference=CoursePreference.from_dict(d.get("preference") or {}),
            existing_schedule=meetings,
            created_at=str(d.get("created_at") or utc_now()),
            updated_at=str(d.get("updated_at") or utc_now()),
        )


@dataclass
class TaskEvent:
    """用户日志事件（计划 §23，非终端垃圾）。"""

    event_id: str
    intent_id: str
    ts: str = field(default_factory=utc_now)
    level: str = "info"  # info / warn / error / success
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "intent_id": self.intent_id,
            "ts": self.ts,
            "level": self.level,
            "message": self.message,
        }
