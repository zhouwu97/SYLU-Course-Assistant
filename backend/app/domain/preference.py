"""用户偏好模型（计划 §七、§八）。

CoursePreference 描述"想上什么课、能接受到什么程度"：
- 首选：教学班 / 教师 / 时间 / 地点
- 排除：教师 / 时间 / 地点（黑名单，绝对不选）
- 替代：是否允许换老师 / 换时间，替代顺序
- 硬开关：排除课表冲突、排除已满、排除人数未知、排除只剩 1 个名额的班

注意：黑名单是 Hard Constraint，优先于一切偏好；即使首选教学班的老师上了黑名单，
也不能自动提交。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schedule import TimeRange, parse_time_range

# 替代层级（tier）
TIER_PREFERRED = 0  # 首选教学班
TIER_SAME_TEACHER_OTHER_TIME = 1  # 同教师、换时间
TIER_OTHER_TEACHER_SAME_TIME = 2  # 换教师、同时间
TIER_OTHER_TEACHER_OTHER_TIME = 3  # 换教师、换时间

DEFAULT_FALLBACK_ORDER = [
    "same_teacher_other_time",
    "other_teacher_same_time",
    "other_teacher_other_time",
]

FALLBACK_LABELS = {
    TIER_PREFERRED: "首选教学班",
    TIER_SAME_TEACHER_OTHER_TIME: "同教师/换时间",
    TIER_OTHER_TEACHER_SAME_TIME: "换教师/同时间",
    TIER_OTHER_TEACHER_OTHER_TIME: "换教师/换时间",
}


@dataclass
class CoursePreference:
    preferred_sections: list[str] = field(default_factory=list)  # 首选教学班名称（jxbmc）
    preferred_teachers: list[str] = field(default_factory=list)
    preferred_times: list[TimeRange] = field(default_factory=list)
    preferred_places: list[str] = field(default_factory=list)

    avoided_teachers: list[str] = field(default_factory=list)
    avoided_times: list[TimeRange] = field(default_factory=list)
    avoided_places: list[str] = field(default_factory=list)

    allow_other_teacher: bool = True
    allow_other_time: bool = True

    forbid_schedule_conflict: bool = True
    forbid_full: bool = True
    forbid_unknown_capacity: bool = False
    avoid_almost_full: bool = False  # 不选距离容量只剩 1 人的班

    fallback_order: list[str] = field(
        default_factory=lambda: list(DEFAULT_FALLBACK_ORDER)
    )
    max_fallback_depth: int = 3  # 最大自动替代等级（tier 上限）

    # ---- 序列化 -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred": {
                "sections": list(self.preferred_sections),
                "teachers": list(self.preferred_teachers),
                "times": [t.to_label() for t in self.preferred_times],
                "places": list(self.preferred_places),
            },
            "avoid": {
                "teachers": list(self.avoided_teachers),
                "times": [t.to_label() for t in self.avoided_times],
                "places": list(self.avoided_places),
            },
            "fallback": {
                "allow_other_teacher": self.allow_other_teacher,
                "allow_other_time": self.allow_other_time,
                "forbid_schedule_conflict": self.forbid_schedule_conflict,
                "forbid_full": self.forbid_full,
                "forbid_unknown_capacity": self.forbid_unknown_capacity,
                "avoid_almost_full": self.avoid_almost_full,
                "order": list(self.fallback_order),
                "max_fallback_depth": self.max_fallback_depth,
            },
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CoursePreference":
        pref = d.get("preferred") or {}
        avoid = d.get("avoid") or {}
        fb = d.get("fallback") or {}

        def times(raw: Any) -> list[TimeRange]:
            out: list[TimeRange] = []
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, TimeRange):
                        out.append(item)
                    elif isinstance(item, str):
                        t = parse_time_range(item)
                        if t:
                            out.append(t)
            return out

        return cls(
            preferred_sections=[str(x) for x in (pref.get("sections") or [])],
            preferred_teachers=[str(x) for x in (pref.get("teachers") or [])],
            preferred_times=times(pref.get("times")),
            preferred_places=[str(x) for x in (pref.get("places") or [])],
            avoided_teachers=[str(x) for x in (avoid.get("teachers") or [])],
            avoided_times=times(avoid.get("times")),
            avoided_places=[str(x) for x in (avoid.get("places") or [])],
            allow_other_teacher=bool(fb.get("allow_other_teacher", True)),
            allow_other_time=bool(fb.get("allow_other_time", True)),
            forbid_schedule_conflict=bool(fb.get("forbid_schedule_conflict", True)),
            forbid_full=bool(fb.get("forbid_full", True)),
            forbid_unknown_capacity=bool(fb.get("forbid_unknown_capacity", False)),
            avoid_almost_full=bool(fb.get("avoid_almost_full", False)),
            fallback_order=[str(x) for x in (fb.get("order") or DEFAULT_FALLBACK_ORDER)],
            max_fallback_depth=int(fb.get("max_fallback_depth", 3)),
        )

    # ---- 层级计算 ----------------------------------------------------------

    def tier_of(self, section, preferred_section_names: set[str] | None = None) -> int:
        """计算一个教学班所属替代层级。

        tier 语义（计划 §9）：
        - 首选教学班 = TIER_PREFERRED
        - 同教师、换时间 = TIER_SAME_TEACHER_OTHER_TIME
        - 换教师、同时间 = TIER_OTHER_TEACHER_SAME_TIME
        - 换教师、换时间 = TIER_OTHER_TEACHER_OTHER_TIME
        """
        names = preferred_section_names if preferred_section_names is not None else set(self.preferred_sections)
        if section.jxbmc in names or section.jxb_id in names:
            return TIER_PREFERRED

        same_teacher = bool(self.preferred_teachers and section.teacher_name in self.preferred_teachers)
        same_time = any(t.overlaps(m) for t in self.preferred_times for m in section.meetings)

        if same_teacher and not same_time:
            return TIER_SAME_TEACHER_OTHER_TIME
        if same_time and not same_teacher:
            return TIER_OTHER_TEACHER_SAME_TIME
        return TIER_OTHER_TEACHER_OTHER_TIME
