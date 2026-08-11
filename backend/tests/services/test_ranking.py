"""决策引擎测试（计划 §36 要求的核心用例）。

必须覆盖：首选有位置 / 首选满 → 同教师其他时间 / 首选满 → 其他教师同时间 /
教师黑名单 / 时间黑名单 / 所有班满 / 时间冲突 / 替代顺序 / 模式。
"""
import pytest

from app.domain.course import CourseSection, SectionStatus, derive_status
from app.domain.decision import DecisionAction
from app.domain.preference import CoursePreference
from app.domain.schedule import Meeting, parse_time_range
from app.domain.task import AutomationMode, CourseIntent
from app.services.ranking import decide, hard_filter


def sec(
    jxbmc: str,
    teacher: str,
    weekday: int,
    periods: tuple[int, int],
    selected: int | None = 29,
    capacity: int | None = 30,
    weeks: frozenset[int] | None = None,
    place: str = "文体中心",
    meetings: tuple[Meeting, ...] | None = None,
) -> CourseSection:
    m = meetings if meetings is not None else (
        Meeting(weekday=weekday, start_period=periods[0], end_period=periods[1],
                weeks=weeks or frozenset(range(1, 17)), place=place),
    )
    return CourseSection(
        jxb_id=f"jxb-{jxbmc}",
        jxbmc=jxbmc,
        kcmc="体育5",
        teacher_name=teacher,
        meetings=m,
        place=place,
        selected=selected,
        capacity=capacity,
        status=derive_status(selected, capacity),
    )


def full(jxbmc: str, teacher: str, weekday: int, periods: tuple[int, int], **kw) -> CourseSection:
    return sec(jxbmc, teacher, weekday, periods, selected=30, capacity=30, **kw)


def intent(pref: CoursePreference, mode=AutomationMode.AUTO, keyword="羽毛球") -> CourseIntent:
    return CourseIntent(intent_id="i1", keyword=keyword, mode=mode, preference=pref)


def pref(**kw) -> CoursePreference:
    defaults = dict(
        preferred_sections=["羽毛球5-11"],
        preferred_teachers=["孔令宇"],
        preferred_times=[parse_time_range("周五5-6")],
    )
    defaults.update(kw)
    return CoursePreference(**defaults)


class TestHardConstraints:
    def test_blocked_teacher_never_selected(self):
        """计划 §36：黑名单教师永不入选。"""
        sections = [
            sec("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-8", "王XX", 5, (7, 8), selected=10),
        ]
        p = pref(avoided_teachers=["王XX"])
        d = decide(sections, intent(p))
        assert d.action == DecisionAction.AUTO_ENROLL
        assert d.selected_section.jxbmc == "羽毛球5-11"
        names = [c.section.jxbmc for c in d.candidates]
        assert "羽毛球5-8" not in names

    def test_blocked_teacher_beats_preferred_section(self):
        """首选教学班的老师上了黑名单 → 整个班被淘汰（黑名单优先于一切）。"""
        sections = [
            sec("羽毛球5-11", "王XX", 5, (5, 6)),
            sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=10),
        ]
        p = pref(avoided_teachers=["王XX"])
        d = decide(sections, intent(p))
        assert d.selected_section.jxbmc == "羽毛球5-8"

    def test_blocked_time_never_selected(self):
        from app.domain.schedule import parse_time_range

        sections = [
            sec("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-3", "张XX", 1, (1, 2), selected=10),
        ]
        p = pref(avoided_times=[parse_time_range("周一1-2")])
        d = decide(sections, intent(p))
        assert d.selected_section.jxbmc == "羽毛球5-11"
        assert all(c.section.jxbmc != "羽毛球5-3" for c in d.candidates)

    def test_conflicting_section_is_removed(self):
        """计划 §36：课表冲突淘汰。"""
        sections = [
            sec("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-8", "孔令宇", 1, (1, 2), selected=10),
        ]
        schedule = [Meeting(weekday=1, start_period=1, end_period=2)]
        p = pref()
        d = decide(sections, intent(p), my_schedule=schedule)
        assert d.selected_section.jxbmc == "羽毛球5-11"
        assert all(c.section.jxbmc != "羽毛球5-8" for c in d.candidates)

    def test_week_disjoint_no_conflict(self):
        """1-8周 与 9-16周 同星期同节次不冲突（计划 §15）。"""
        sections = [
            sec("羽毛球5-11", "孔令宇", 5, (5, 6), selected=30, capacity=30),
            sec("羽毛球5-8", "孔令宇", 5, (5, 6), selected=10,
                weeks=frozenset(range(9, 17))),
        ]
        schedule = [Meeting(weekday=5, start_period=5, end_period=6,
                            weeks=frozenset(range(1, 9)))]
        p = pref()
        d = decide(sections, intent(p), my_schedule=schedule)
        assert d.selected_section.jxbmc == "羽毛球5-8"

    def test_almost_full_excluded_when_flag_on(self):
        sections = [
            sec("羽毛球5-11", "孔令宇", 5, (5, 6), selected=30, capacity=30),
            sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=29, capacity=30),
        ]
        p = pref(avoid_almost_full=True)
        d = decide(sections, intent(p))
        assert d.action == DecisionAction.NO_ACTION

    def test_unknown_capacity_excluded_when_flag_on(self):
        sections = [sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=None, capacity=None)]
        p = pref(forbid_unknown_capacity=True)
        d = decide(sections, intent(p))
        assert d.action == DecisionAction.NO_ACTION


class TestFallback:
    def test_preferred_section_with_seat_wins(self):
        sections = [
            sec("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=10),
        ]
        d = decide(sections, intent(pref()))
        assert d.selected_section.jxbmc == "羽毛球5-11"
        assert d.candidates[0].tier == 0

    def test_full_preferred_section_falls_back(self):
        """计划 §36：首选满 → 同教师其他时间。"""
        sections = [
            full("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=10),
            sec("羽毛球5-3", "李XX", 5, (5, 6), selected=10),
        ]
        d = decide(sections, intent(pref()))
        assert d.selected_section.jxbmc == "羽毛球5-8"
        assert d.candidates[0].tier == 0  # 首选班仍排第一（已满，被跳过）
        assert d.candidates[1].tier == 1

    def test_same_teacher_other_time_before_other_teacher(self):
        """计划 §36：同教师其他时间优先于其他教师同时间。"""
        sections = [
            full("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=10),
            sec("羽毛球5-3", "李XX", 5, (5, 6), selected=10),
            sec("羽毛球5-5", "张XX", 3, (3, 4), selected=10),
        ]
        d = decide(sections, intent(pref()))
        order = [c.section.jxbmc for c in d.candidates]
        assert order.index("羽毛球5-8") < order.index("羽毛球5-3")
        assert order.index("羽毛球5-8") < order.index("羽毛球5-5")

    def test_preferred_teacher_beats_other_teacher(self):
        """计划 §36：同层级内首选教师胜出。"""
        sections = [
            full("羽毛球5-11", "孔令宇", 5, (5, 6)),
            full("羽毛球5-8", "孔令宇", 5, (7, 8)),
            sec("羽毛球5-3", "李XX", 5, (5, 6), selected=10),
            sec("羽毛球5-2", "孔令宇", 3, (3, 4), selected=10),
        ]
        d = decide(sections, intent(pref()))
        # 首选教师、换时间换星期 的 5-2 应排在 换教师的 5-3 前面
        order = [c.section.jxbmc for c in d.candidates]
        assert order.index("羽毛球5-2") < order.index("羽毛球5-3")

    def test_all_sections_full_no_action(self):
        """计划 §36：所有班满 → NO_ACTION，不瞎选。"""
        sections = [
            full("羽毛球5-11", "孔令宇", 5, (5, 6)),
            full("羽毛球5-8", "孔令宇", 5, (7, 8)),
            full("羽毛球5-3", "李XX", 5, (5, 6)),
        ]
        d = decide(sections, intent(pref()))
        assert d.action == DecisionAction.NO_ACTION
        assert d.selected_section is None
        assert len(d.candidates) == 3  # 已满班仍展示

    def test_fallback_order_respected(self):
        """用户自定义替代顺序：换教师同时间排第一。"""
        sections = [
            full("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=10),
            sec("羽毛球5-3", "李XX", 5, (5, 6), selected=10),
        ]
        p = pref(fallback_order=["other_teacher_same_time", "same_teacher_other_time", "other_teacher_other_time"])
        d = decide(sections, intent(p))
        assert d.selected_section.jxbmc == "羽毛球5-3"

    def test_no_other_teacher_allowed(self):
        sections = [
            full("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=10),
            sec("羽毛球5-3", "李XX", 5, (5, 6), selected=10),
        ]
        p = pref(allow_other_teacher=False)
        d = decide(sections, intent(p))
        assert d.selected_section.jxbmc == "羽毛球5-8"
        assert all(c.section.teacher_name == "孔令宇" for c in d.candidates)

    def test_no_other_time_allowed(self):
        sections = [
            full("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=10),
            sec("羽毛球5-3", "孔令宇", 5, (5, 6), selected=10),
        ]
        p = pref(allow_other_time=False)
        d = decide(sections, intent(p))
        assert d.selected_section.jxbmc == "羽毛球5-3"
        assert all(c.section.jxbmc in ("羽毛球5-11", "羽毛球5-3") for c in d.candidates)

    def test_max_fallback_depth(self):
        sections = [
            full("羽毛球5-11", "孔令宇", 5, (5, 6)),
            sec("羽毛球5-8", "孔令宇", 5, (7, 8), selected=10),
            sec("羽毛球5-3", "李XX", 5, (5, 6), selected=10),
        ]
        p = pref(max_fallback_depth=1)
        d = decide(sections, intent(p))
        assert d.selected_section.jxbmc == "羽毛球5-8"
        assert all(c.tier <= 1 for c in d.candidates)


class TestReasonsAndModes:
    def test_reasons_explain_choice(self):
        sections = [sec("羽毛球5-11", "孔令宇", 5, (5, 6))]
        d = decide(sections, intent(pref()))
        reasons = d.candidates[0].reasons
        assert "首选教学班" in reasons
        assert "不与课表冲突" in reasons

    def test_notify_mode_never_enrolls(self):
        sections = [sec("羽毛球5-11", "孔令宇", 5, (5, 6))]
        d = decide(sections, intent(pref(), mode=AutomationMode.NOTIFY))
        assert d.action == DecisionAction.NOTIFY
        assert d.selected_section is not None

    def test_confirm_mode_waits(self):
        sections = [sec("羽毛球5-11", "孔令宇", 5, (5, 6))]
        d = decide(sections, intent(pref(), mode=AutomationMode.CONFIRM))
        assert d.action == DecisionAction.WAIT_CONFIRM

    def test_auto_mode_enrolls(self):
        sections = [sec("羽毛球5-11", "孔令宇", 5, (5, 6))]
        d = decide(sections, intent(pref(), mode=AutomationMode.AUTO))
        assert d.action == DecisionAction.AUTO_ENROLL

    def test_requested_carries_preferences(self):
        sections = [sec("羽毛球5-11", "孔令宇", 5, (5, 6))]
        d = decide(sections, intent(pref()))
        assert d.requested["teacher"] == "孔令宇"
        assert d.requested["sections"] == "羽毛球5-11"
