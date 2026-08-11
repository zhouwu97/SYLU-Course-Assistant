"""课表时间模型与冲突引擎（计划 §15）。

统一模型：
- weekday: 1=周一 ... 7=周日
- start_period / end_period: 节次
- weeks: 实际周次集合（不是字符串，避免 "星期五5-6" 式字符串比较）

两条 Meeting 冲突当且仅当：周次有交集 且 星期相同 且 节次区间重叠。
例如 "1-8周 星期五5-6节" 与 "9-16周 星期五5-6节" 不冲突。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

DEFAULT_WEEKS = frozenset(range(1, 17))  # 无周次信息时的默认全学期

_CN_WEEKDAY = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
}
_WEEKDAY_RE = re.compile(
    r"(?:星期|周|礼拜)([一二三四五六日天1-7])"
)

# 周次区间必须带"周"字，避免把 "5-6节" 的节次区间误判成周次
_WEEK_RANGE_RE = re.compile(r"(\d{1,2})\s*[-~至—]\s*(\d{1,2})\s*周")
_WEEK_SINGLE_RE = re.compile(r"(\d{1,2})\s*周")
_PERIOD_RANGE_RE = re.compile(r"(?:第)?(\d{1,2})\s*[-~至—]\s*(\d{1,2})\s*节?")
_PERIOD_SINGLE_RE = re.compile(r"(?:第)?(\d{1,2})\s*节?")


def parse_weekday(text: str) -> int | None:
    """'星期五' / '周五' / '星期5' / '周5' -> 5；解析失败返回 None。"""
    m = _WEEKDAY_RE.search(text)
    if not m:
        return None
    token = m.group(1)
    if token.isdigit():
        return int(token)
    return _CN_WEEKDAY.get(token)


def parse_periods(text: str) -> tuple[int, int] | None:
    """'5-6节' -> (5, 6)；'第3节' -> (3, 3)；解析失败返回 None。"""
    m = _PERIOD_RANGE_RE.search(text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = _PERIOD_SINGLE_RE.search(text)
    if m:
        v = int(m.group(1))
        return (v, v)
    return None


def parse_weeks(text: str) -> frozenset[int] | None:
    """从 '1-16周' / '1-8,10-16周' / '1-16周(单)' / '全周' 解析周次集合。

    单周=奇数周，双周=偶数周。无有效信息返回 None（由调用方决定默认值）。
    """
    if not text:
        return None
    if "全周" in text or "全程" in text:
        return DEFAULT_WEEKS
    if not re.search(r"\d", text):
        return None

    parity: str | None = None
    if re.search(r"单", text):
        parity = "odd"
    elif re.search(r"双", text):
        parity = "even"

    result: set[int] = set()
    text_has_zhou = "周" in text
    for seg in re.split(r"[,,，;；、]", text):
        m = _WEEK_RANGE_RE.search(seg)  # 带"周"的区间，如 "1-8周"
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            lo, hi = min(a, b), max(a, b)
            for w in range(lo, hi + 1):
                if parity == "odd" and w % 2 == 0:
                    continue
                if parity == "even" and w % 2 == 1:
                    continue
                result.add(w)
            continue
        m2 = _WEEK_SINGLE_RE.search(seg)  # 带"周"的单周，如 "3周"
        if m2:
            result.add(int(m2.group(1)))
            continue
        if not text_has_zhou:
            continue  # 整串没有周次信息（如纯节次 "5-6节"），跳过
        # 段内出现"周"上下文但无直接匹配（如逗号分段 "1-8" 与 "10-16周"），按数字区间兜底
        m3 = re.search(r"(\d{1,2})\s*[-~至—]\s*(\d{1,2})", seg)
        if m3:
            a, b = int(m3.group(1)), int(m3.group(2))
            for w in range(min(a, b), max(a, b) + 1):
                if parity == "odd" and w % 2 == 0:
                    continue
                if parity == "even" and w % 2 == 1:
                    continue
                result.add(w)
            continue
        m4 = re.search(r"\d{1,2}", seg)
        if m4:
            result.add(int(m4.group()))
    return frozenset(result) if result else None


@dataclass(frozen=True)
class Meeting:
    """一次上课安排。"""

    weekday: int  # 1=周一 ... 7=周日
    start_period: int
    end_period: int
    weeks: frozenset[int] = field(default_factory=lambda: DEFAULT_WEEKS)
    place: str = ""


def periods_overlap(
    a_start: int, a_end: int, b_start: int, b_end: int
) -> bool:
    return a_start <= b_end and b_start <= a_end


def meetings_conflict(a: Meeting, b: Meeting) -> bool:
    """周次有交集 且 星期相同 且 节次重叠。"""
    if a.weekday != b.weekday:
        return False
    if a.weeks.isdisjoint(b.weeks):
        return False
    return periods_overlap(a.start_period, a.end_period, b.start_period, b.end_period)


def schedule_conflicts(
    meetings_a: Iterable[Meeting], meetings_b: Iterable[Meeting]
) -> bool:
    """两组课表之间是否存在任意一对冲突。"""
    list_b = list(meetings_b)
    for ma in meetings_a:
        for mb in list_b:
            if meetings_conflict(ma, mb):
                return True
    return False


@dataclass(frozen=True)
class TimeRange:
    """偏好用的时间段：某星期的节次区间（周次无关）。"""

    weekday: int
    start_period: int
    end_period: int

    def overlaps(self, m: Meeting) -> bool:
        return (
            self.weekday == m.weekday
            and periods_overlap(self.start_period, self.end_period, m.start_period, m.end_period)
        )

    def to_label(self) -> str:
        nums = ["一", "二", "三", "四", "五", "六", "日"]
        name = nums[self.weekday - 1] if 1 <= self.weekday <= 7 else str(self.weekday)
        return f"周{name}{self.start_period}-{self.end_period}节"


def parse_time_range(text: str) -> TimeRange | None:
    """'周五5-6' / '星期五5-6节' -> TimeRange(5,5,6)。解析失败返回 None。"""
    weekday = parse_weekday(text)
    periods = parse_periods(text)
    if weekday is None or periods is None:
        return None
    return TimeRange(weekday, periods[0], periods[1])


def parse_meeting(
    text: str, *, default_weeks: frozenset[int] | None = None
) -> Meeting | None:
    """从 '星期五5-6节(1-8周)' 之类文本解析 Meeting。

    无周次信息时使用 default_weeks，再退回 DEFAULT_WEEKS（全学期）。
    """
    weekday = parse_weekday(text)
    periods = parse_periods(text)
    if weekday is None or periods is None:
        return None
    weeks = parse_weeks(text)
    if weeks is None:
        weeks = default_weeks if default_weeks is not None else DEFAULT_WEEKS
    return Meeting(weekday=weekday, start_period=periods[0], end_period=periods[1], weeks=weeks)
