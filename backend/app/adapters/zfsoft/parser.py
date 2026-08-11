"""正方教务系统页面/接口解析器（计划 §5、§二十）。

只做"把页面数据变成领域对象"：JSON 列表接口、DOM 行、文本块、提交结果分类。
输出是 CourseSection / Meeting / EnrollResult，不含任何业务判断。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.domain.course import CourseSection, derive_status
from app.domain.schedule import (
    Meeting,
    parse_meeting,
    parse_periods,
    parse_weekday,
    parse_weeks,
)

# ---- 字段别名：同一业务字段在正方不同部署里的不同名字 --------------------

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "jxb_id": ("jxb_id", "jxbid"),
    "jxbmc": ("jxbmc",),
    "kch": ("kch",),
    "kch_id": ("kch_id", "kchid"),
    "kcmc": ("kcmc",),
    "teacher": ("rkjs", "jsxx", "jsxm", "jsmc"),
    "place": ("skdd", "jxdd", "dd", "skddmc"),
    "skxq": ("skxq", "xq", "xqmc"),
    "skjc": ("skjc", "jc", "skjcmc"),
    "skzc": ("skzc", "zc", "zxsj", "sksj"),
    "selected": ("sxr", "yxrs", "xrs", "xjs"),
    "capacity": ("yxzrs", "rxs", "zrs", "jrs"),
}

# 星期/节次组合文本（含周次）
_WEEKDAY_SPLIT_RE = re.compile(r"(?=星期[一二三四五六日天1-7]|周[一二三四五六日天1-7])")


def _get(row: dict[str, Any], key: str) -> str:
    for alias in _FIELD_ALIASES.get(key, ()):
        v = row.get(alias)
        if v is not None and str(v).strip() not in ("", "None", "null"):
            return str(v).strip()
    return ""


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _meetings_from_row(row: dict[str, Any]) -> list[Meeting]:
    """从 JSON 行提取上课安排。

    兼容两种格式：
    - skxq="星期五", skjc="5-6节", skzc="1-16周"
    - skjc 自带星期与周次： "星期五5-6节{1-16周}"
    一个行里可能有多个时间（逗号/分号分隔或连续星期文本）。
    """
    skxq = _get(row, "skxq")
    skjc = _get(row, "skjc")
    skzc = _get(row, "skzc")
    place = _get(row, "place")

    week_text = skzc if re.search(r"\d", skzc) else ""

    # skjc 中可能直接带星期（一个或多个）
    parts: list[str] = []
    if re.search(r"星期[一二三四五六日天1-7]|周[一二三四五六日天1-7]", skjc):
        parts = [p for p in _WEEKDAY_SPLIT_RE.split(skjc) if p.strip()]
    elif skxq:
        parts = [skjc or ""]
    if not parts:
        return []

    meetings: list[Meeting] = []
    for part in parts:
        full = part if parse_weekday(part) else f"{skxq} {part}".strip()
        if week_text:
            full = f"{full} {week_text}".strip()
        m = parse_meeting(full)
        if m is None:
            continue
        # 显式周次字段优先（skjc 内嵌的周次可能与 skzc 不同）
        if week_text:
            weeks = parse_weeks(week_text)
            if weeks is not None:
                m = Meeting(m.weekday, m.start_period, m.end_period, weeks, place)
            else:
                m = Meeting(m.weekday, m.start_period, m.end_period, m.weeks, place)
        meetings.append(m)
    return meetings


def parse_sections_from_items(items: list[dict[str, Any]], course_hint: str = "") -> list[CourseSection]:
    """解析选课列表接口返回的 items。

    同一 jxb_id 可能出现多行（每行一个上课时间），按 jxb_id 归并教学班。
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in items:
        jxb_id = _get(row, "jxb_id")
        key = jxb_id or _get(row, "jxbmc") or f"row-{len(grouped)}"
        grouped.setdefault(key, []).append(row)

    out: list[CourseSection] = []
    for rows in grouped.values():
        first = rows[0]
        meetings: list[Meeting] = []
        for r in rows:
            meetings.extend(_meetings_from_row(r))

        selected = _to_int(_get(first, "selected"))
        capacity = _to_int(_get(first, "capacity"))

        out.append(
            CourseSection(
                jxb_id=_get(first, "jxb_id"),
                jxbmc=_get(first, "jxbmc"),
                kch=_get(first, "kch"),
                kch_id=_get(first, "kch_id"),
                kcmc=_get(first, "kcmc") or course_hint,
                teacher_name=_get(first, "teacher"),
                meetings=tuple(meetings),
                place=_get(first, "place"),
                selected=selected,
                capacity=capacity,
                status=derive_status(selected, capacity),
            )
        )
    return out


# ---- DOM 行 / 文本块启发式解析（XHR 不可用时的降级路径） --------------------

_JXBMC_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9（）()]*\d+-\d+")
_CAP_SLASH_RE = re.compile(r"(\d{1,4})\s*/\s*(\d{1,4})")
_NUM_ONLY_RE = re.compile(r"^\d{1,4}$")
_PLACE_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]*[馆楼室厅中心场区园]")
_WEEKDAY_WORDS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日", "周日", "周六", "周五", "周一", "周二", "周三", "周四")


def parse_sections_from_dom_rows(rows: list[list[str]], course_hint: str = "") -> list[CourseSection]:
    """从 DOM 表格行（每行是各单元格文本）解析教学班。降级路径。"""
    out: list[CourseSection] = []
    for idx, cells in enumerate(rows):
        jxbmc = ""
        teacher = ""
        time_text = ""
        place = ""
        cap_candidates: list[tuple[int, int]] = []
        numeric_cells: list[int] = []
        for cell in cells:
            cell = " ".join(cell.split())
            if not cell:
                continue
            if not jxbmc and _JXBMC_RE.search(cell):
                jxbmc = _JXBMC_RE.search(cell).group()
                continue
            if not time_text and parse_meeting(cell):
                time_text = cell
                continue
            if not place and _PLACE_RE.fullmatch(cell) and len(cell) <= 12:
                place = cell
                continue
            m = _CAP_SLASH_RE.search(cell)
            if m:
                cap_candidates.append((int(m.group(1)), int(m.group(2))))
                continue
            if _NUM_ONLY_RE.match(cell):
                numeric_cells.append(int(cell))
                continue
            if not teacher and len(cell) <= 4 and not re.search(r"\d", cell) and cell not in _WEEKDAY_WORDS and cell not in ("已满", "可选", "选课", "退选"):
                teacher = cell
        if not jxbmc:
            continue
        selected = capacity = None
        if cap_candidates:
            selected, capacity = cap_candidates[0]
        elif len(numeric_cells) >= 2:
            # 已选/容量是独立数字单元格时，取最后两个（接近行尾的动作按钮）
            selected, capacity = numeric_cells[-2], numeric_cells[-1]
        status = derive_status(selected, capacity)
        out.append(
            CourseSection(
                jxb_id=f"dom:{jxbmc}:{idx}",
                jxbmc=jxbmc,
                kcmc=course_hint,
                teacher_name=teacher,
                meetings=(parse_meeting(time_text),) if time_text and parse_meeting(time_text) else (),
                place=place,
                selected=selected,
                capacity=capacity,
                status=status,
            )
        )
    return out


def parse_section_from_text(blob: str, course_hint: str = "") -> CourseSection | None:
    """从"选课"按钮祖先容器文本块解析教学班（v2 的思路，结构化输出）。"""
    blob = " ".join(blob.split())
    m = _JXBMC_RE.search(blob)
    if not m:
        return None
    jxbmc = m.group()

    teacher = ""
    time_text = ""
    place = ""
    selected = capacity = None

    for token in re.split(r"[\s|｜,，;；]+", blob):
        token = token.strip()
        if not token:
            continue
        if not time_text and parse_meeting(token):
            time_text = token
            continue
        cm = _CAP_SLASH_RE.search(token)
        if cm:
            selected, capacity = int(cm.group(1)), int(cm.group(2))
            continue
        if not place and _PLACE_RE.fullmatch(token) and len(token) <= 12:
            place = token
            continue
        if not teacher and len(token) <= 4 and not re.search(r"\d", token) and token not in _WEEKDAY_WORDS and token not in ("已满", "可选", "选课", "退选", "报名"):
            teacher = token

    status = derive_status(selected, capacity)
    meeting = parse_meeting(time_text) if time_text else None
    return CourseSection(
        jxb_id=f"dom:{jxbmc}",
        jxbmc=jxbmc,
        kcmc=course_hint,
        teacher_name=teacher,
        meetings=(meeting,) if meeting else (),
        place=place,
        selected=selected,
        capacity=capacity,
        status=status,
    )


# ---- 提交结果分类（计划 §19、§20） ------------------------------------------

class EnrollOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FULL = "FULL"  # section-level：继续找其他班
    CONFLICT = "CONFLICT"  # section-level：该班不可用，继续候选
    REJECTED = "REJECTED"  # 视消息判断 section-level 或 course-level
    SESSION_EXPIRED = "SESSION_EXPIRED"  # course/system-level：暂停任务
    NETWORK_ERROR = "NETWORK_ERROR"  # system-level：退避重试
    UNKNOWN = "UNKNOWN"


_SUCC_WORDS = ("选课成功", "选择成功", "操作成功", "成功", "已选")
_FULL_WORDS = ("人数已满", "课程已满", "已满", "无余量", "余量不足", "容量已满", "名额已满")
_CONFLICT_WORDS = ("时间冲突", "节次冲突", "上课时间冲突", "冲突")
_REJECT_WORDS = ("不满足", "不能选", "不可选", "失败", "超过", "已选过", "重复", "资格", "不允许", "限选")
_SESSION_WORDS = ("未登录", "登录已失效", "登录失效", "请重新登录", "重新登录", "会话失效")
_NETWORK_WORDS = ("网络", "繁忙", "稍后重试", "服务器", "系统繁忙", "超时")


@dataclass
class EnrollResult:
    outcome: EnrollOutcome
    message: str
    endpoint: str = ""

    @property
    def is_section_level(self) -> bool:
        """计划 §20：FULL/CONFLICT 永远 section-level；REJECTED 看消息。"""
        if self.outcome in (EnrollOutcome.FULL, EnrollOutcome.CONFLICT):
            return True
        if self.outcome == EnrollOutcome.REJECTED:
            # 资格/限制类拒绝 -> course-level（暂停整门课）；单班被拒 -> section-level
            return not any(w in self.message for w in ("资格", "不允许", "限制"))
        return False

    @property
    def ok(self) -> bool:
        return self.outcome == EnrollOutcome.SUCCESS


def classify_enroll_result(data: dict[str, Any], page_text: str = "") -> EnrollResult:
    """分类服务器提交响应。与 v2 的区别：结构化 outcome 而不是 success/retry/stop。"""
    msg = str(data.get("msg") or data.get("message") or data.get("text") or "").strip()
    flag = str(data.get("flag", "")).strip()
    combined = (msg + " " + page_text[-2500:]).strip()

    if flag == "1" or any(w in combined for w in _SUCC_WORDS):
        return EnrollResult(EnrollOutcome.SUCCESS, msg or "服务器返回成功")
    if any(w in combined for w in _FULL_WORDS):
        return EnrollResult(EnrollOutcome.FULL, msg or "教学班已满")
    if any(w in combined for w in _CONFLICT_WORDS):
        return EnrollResult(EnrollOutcome.CONFLICT, msg or "时间冲突")
    if any(w in combined for w in _REJECT_WORDS):
        return EnrollResult(EnrollOutcome.REJECTED, msg or "选课被拒绝")
    if any(w in combined for w in _SESSION_WORDS):
        return EnrollResult(EnrollOutcome.SESSION_EXPIRED, msg or "登录已失效")
    if any(w in combined for w in _NETWORK_WORDS):
        return EnrollResult(EnrollOutcome.NETWORK_ERROR, msg or "服务器繁忙/网络异常")
    if flag and flag != "1":
        return EnrollResult(EnrollOutcome.UNKNOWN, msg or f"服务器 flag={flag}")
    return EnrollResult(EnrollOutcome.UNKNOWN, msg or "未识别服务器反馈")
