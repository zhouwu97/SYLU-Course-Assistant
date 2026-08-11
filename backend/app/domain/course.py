"""课程 / 教学班领域模型（计划 §5、§二十）。

CourseSection 是业务层唯一可见的教学班视图；jxb_id 等正方字段只在这里作为
不透明标识符出现，不参与任何业务判断。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from .schedule import Meeting, schedule_conflicts


class SectionStatus(str, Enum):
    """教学班余量状态（计划 §二十：section-level 状态）。"""

    UNKNOWN = "UNKNOWN"  # 已选人数未知
    AVAILABLE = "AVAILABLE"  # 已知且有余量
    FULL = "FULL"  # 已知且已满


def derive_status(selected: int | None, capacity: int | None) -> SectionStatus:
    """按服务器返回的 已选/容量 推导状态。

    这一字段是动态数据（计划 §28），每次查询都要重新推导。
    """
    if selected is None or capacity is None:
        return SectionStatus.UNKNOWN
    if selected >= capacity:
        return SectionStatus.FULL
    return SectionStatus.AVAILABLE


@dataclass(frozen=True)
class CourseSection:
    """一个教学班。字段语义来自业务，不绑定正方页面结构。"""

    jxb_id: str  # 教学班唯一 id（正方内部标识，对业务层不透明）
    jxbmc: str  # 教学班名称，如 "羽毛球5-11"
    kch: str = ""  # 课程号
    kch_id: str = ""  # 课程 id
    kcmc: str = ""  # 课程名称，如 "体育5"
    teacher_name: str = ""
    meetings: tuple[Meeting, ...] = ()
    place: str = ""
    selected: int | None = None  # 已选人数
    capacity: int | None = None  # 容量
    status: SectionStatus = SectionStatus.UNKNOWN

    @property
    def availability_text(self) -> str:
        if self.selected is None or self.capacity is None:
            return "人数未知"
        return f"{self.selected}/{self.capacity}"

    @property
    def is_full(self) -> bool:
        return self.status == SectionStatus.FULL

    @property
    def has_seat(self) -> bool:
        """已知且有余量。"""
        return self.status == SectionStatus.AVAILABLE

    def conflicts_with(self, schedule: Iterable[Meeting]) -> bool:
        """与给定课表是否存在时间冲突。"""
        if not self.meetings:
            return False
        return schedule_conflicts(self.meetings, schedule)

    def matches_teacher(self, name: str) -> bool:
        return name and self.teacher_name == name

    def to_dict(self) -> dict:
        return {
            "jxb_id": self.jxb_id,
            "jxbmc": self.jxbmc,
            "kch": self.kch,
            "kch_id": self.kch_id,
            "kcmc": self.kcmc,
            "teacher": self.teacher_name,
            "meetings": [
                {
                    "weekday": m.weekday,
                    "start_period": m.start_period,
                    "end_period": m.end_period,
                    "weeks": sorted(m.weeks),
                    "place": m.place,
                }
                for m in self.meetings
            ],
            "place": self.place,
            "selected": self.selected,
            "capacity": self.capacity,
            "status": self.status.value,
        }


@dataclass
class Course:
    """一门课程（含其全部教学班）。"""

    kch_id: str = ""
    kch: str = ""
    name: str = ""
    category: str = ""
    sections: list[CourseSection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kch_id": self.kch_id,
            "kch": self.kch,
            "name": self.name,
            "category": self.category,
            "section_count": len(self.sections),
            "sections": [s.to_dict() for s in self.sections],
        }
