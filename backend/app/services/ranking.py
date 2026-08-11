"""决策引擎（计划 §9、§十、§37、§38）。

流水线：Hard Constraints → 过滤 → Fallback Tier → Preference Score → Availability → 排序。

绝不写"找不到首选就点页面第一个有余量的班"。自动提交必须同时满足：
CourseIntent + Hard Constraints + Fallback permission + Candidate ranking + Current availability。
"""
from __future__ import annotations

from app.domain.course import CourseSection
from app.domain.decision import Candidate, Decision, DecisionAction
from app.domain.preference import (
    FALLBACK_LABELS,
    TIER_OTHER_TEACHER_OTHER_TIME,
    TIER_OTHER_TEACHER_SAME_TIME,
    TIER_PREFERRED,
    TIER_SAME_TEACHER_OTHER_TIME,
    CoursePreference,
)
from app.domain.schedule import Meeting
from app.domain.task import AutomationMode, CourseIntent

# 层级基础分（计划 §9）
_TIER_BASE = {
    TIER_PREFERRED: 100,
    TIER_SAME_TEACHER_OTHER_TIME: 85,
    TIER_OTHER_TEACHER_SAME_TIME: 75,
    TIER_OTHER_TEACHER_OTHER_TIME: 60,
}

# tier 内加分（只影响同层级排序，不影响层级次序）
_BONUS_PREFERRED_TEACHER = 4
_BONUS_PREFERRED_TIME = 4
_BONUS_PREFERRED_PLACE = 2
_BONUS_HAS_SEAT = 2


def _fallback_rank(preference: CoursePreference) -> dict[int, int]:
    """把用户配置的替代顺序映射为 tier 排序权重（越小越优先）。"""
    rank = {TIER_PREFERRED: 0}
    order = preference.fallback_order
    for i, name in enumerate(order, start=1):
        if name == "same_teacher_other_time":
            rank[TIER_SAME_TEACHER_OTHER_TIME] = i
        elif name == "other_teacher_same_time":
            rank[TIER_OTHER_TEACHER_SAME_TIME] = i
        elif name == "other_teacher_other_time":
            rank[TIER_OTHER_TEACHER_OTHER_TIME] = i
    # 未出现在顺序里的层级按默认顺序排在最后
    default = [TIER_SAME_TEACHER_OTHER_TIME, TIER_OTHER_TEACHER_SAME_TIME, TIER_OTHER_TEACHER_OTHER_TIME]
    next_rank = len(order) + 1
    for tier in default:
        rank.setdefault(tier, next_rank)
        next_rank += 1
    return rank


def _in_avoided_times(section: CourseSection, preference: CoursePreference) -> bool:
    return any(
        tr.overlaps(m) for tr in preference.avoided_times for m in section.meetings
    )


def _hits_preferred_time(section: CourseSection, preference: CoursePreference) -> bool:
    return any(
        tr.overlaps(m) for tr in preference.preferred_times for m in section.meetings
    )


def hard_filter(
    sections: list[CourseSection],
    preference: CoursePreference,
    my_schedule: list[Meeting] | None = None,
) -> list[CourseSection]:
    """Hard Constraints（计划 §9、§七）。黑名单优先于一切偏好。

    注意：满员班不在这里过滤——它们仍进入 candidates 用于展示（计划 §38 显示
    首选满员班并标记 FULL），但决策门 has_seat 保证绝不选中已满班。
    """
    schedule = my_schedule or []
    preferred_names = set(preference.preferred_sections)
    out: list[CourseSection] = []
    for s in sections:
        is_preferred_section = s.jxbmc in preferred_names or s.jxb_id in preferred_names
        # 黑名单：教师 / 时间 / 地点 —— 绝对不选
        if preference.avoided_teachers and s.teacher_name in preference.avoided_teachers:
            continue
        if _in_avoided_times(s, preference):
            continue
        if preference.avoided_places and any(p in s.place for p in preference.avoided_places):
            continue
        # 替代权限
        if not is_preferred_section:
            if not preference.allow_other_teacher and not (
                preference.preferred_teachers and s.teacher_name in preference.preferred_teachers
            ):
                continue
            if not preference.allow_other_time and not _hits_preferred_time(s, preference):
                continue
        # 容量硬开关（已满由决策门单独处理）
        if preference.forbid_unknown_capacity and s.status.value == "UNKNOWN":
            continue
        if preference.avoid_almost_full and s.selected is not None and s.capacity is not None:
            if s.capacity - s.selected == 1:
                continue
        # 课表冲突
        if preference.forbid_schedule_conflict and s.conflicts_with(schedule):
            continue
        out.append(s)
    return out


def _score_section(
    s: CourseSection,
    preference: CoursePreference,
    tier: int,
    reasons: list[str],
) -> int:
    score = _TIER_BASE.get(tier, 60)
    if tier != TIER_PREFERRED:
        if preference.preferred_teachers and s.teacher_name in preference.preferred_teachers:
            score += _BONUS_PREFERRED_TEACHER
            reasons.append("首选教师")
        if _hits_preferred_time(s, preference):
            score += _BONUS_PREFERRED_TIME
            reasons.append("首选时间")
    if preference.preferred_places and any(p in s.place for p in preference.preferred_places):
        score += _BONUS_PREFERRED_PLACE
        reasons.append("首选地点")
    if s.has_seat:
        score += _BONUS_HAS_SEAT
        reasons.append(f"当前还有 {s.capacity - s.selected} 个名额" if s.capacity is not None else "当前有余量")
    return score


def decide(
    sections: list[CourseSection],
    intent: CourseIntent,
    my_schedule: list[Meeting] | None = None,
) -> Decision:
    """对全部教学班做决策。candidates 按 (层级顺序, -分数) 排序，含已满班；
    decision 只选第一个有余量的班（计划 §38）。"""
    preference = intent.preference
    schedule = my_schedule if my_schedule is not None else intent.existing_schedule
    tier_rank = _fallback_rank(preference)

    eligible = hard_filter(sections, preference, schedule)
    preferred_names = set(preference.preferred_sections)

    candidates: list[Candidate] = []
    for s in eligible:
        tier = preference.tier_of(s, preferred_names)
        if tier > preference.max_fallback_depth:
            continue
        reasons: list[str] = []
        if tier == TIER_PREFERRED:
            reasons.append("首选教学班")
        if preference.forbid_schedule_conflict and not s.conflicts_with(schedule):
            reasons.append("不与课表冲突")
        elif preference.forbid_schedule_conflict:
            reasons.append("与课表冲突")
        if tier != TIER_PREFERRED:
            label = FALLBACK_LABELS.get(tier, "替代")
            same_teacher = bool(
                preference.preferred_teachers and s.teacher_name in preference.preferred_teachers
            )
            same_time = _hits_preferred_time(s, preference)
            if same_teacher and same_time:
                reasons.append("同教师/同首选时间")
            elif tier == TIER_SAME_TEACHER_OTHER_TIME:
                reasons.append("同教师/换时间")
            elif tier == TIER_OTHER_TEACHER_SAME_TIME:
                reasons.append("换教师/同时间")
            elif tier == TIER_OTHER_TEACHER_OTHER_TIME:
                reasons.append("换教师/换时间")
            else:
                reasons.append(label)
        score = _score_section(s, preference, tier, reasons)
        if s.status.value == "UNKNOWN":
            reasons.append("人数未知")
        candidates.append(Candidate(section=s, tier=tier, score=score, reasons=reasons))

    candidates.sort(key=lambda c: (tier_rank.get(c.tier, 99), -c.score))

    # 决策：选第一个有余量的班（计划 §37 硬门槛）
    selected = next((c.section for c in candidates if c.section.has_seat), None)

    requested = {
        "activity": intent.keyword or intent.course_name,
        "teacher": "、".join(preference.preferred_teachers) or None,
        "time": "、".join(t.to_label() for t in preference.preferred_times) or None,
        "sections": "、".join(preference.preferred_sections) or None,
    }

    if selected is None:
        message = "当前没有满足策略的可选教学班"
        action = DecisionAction.NO_ACTION
    elif intent.mode == AutomationMode.NOTIFY:
        message = f"发现可选教学班 {selected.jxbmc}（仅提醒）"
        action = DecisionAction.NOTIFY
    elif intent.mode == AutomationMode.CONFIRM:
        message = f"发现可选教学班 {selected.jxbmc}，等待确认"
        action = DecisionAction.WAIT_CONFIRM
    else:
        message = f"自动选择 {selected.jxbmc}"
        action = DecisionAction.AUTO_ENROLL

    return Decision(
        intent_id=intent.intent_id,
        requested=requested,
        candidates=candidates,
        action=action,
        selected_section=selected,
        message=message,
    )
