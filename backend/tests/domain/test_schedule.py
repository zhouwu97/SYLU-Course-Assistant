"""课表冲突引擎与时间解析测试（计划 §15、§36）。"""
import pytest

from app.domain.schedule import (
    DEFAULT_WEEKS,
    Meeting,
    meetings_conflict,
    parse_meeting,
    parse_periods,
    parse_time_range,
    parse_weekday,
    parse_weeks,
    periods_overlap,
    schedule_conflicts,
)


class TestParseWeekday:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("星期一", 1),
            ("周五", 5),
            ("星期五", 5),
            ("星期日", 7),
            ("周日", 7),
            ("星期天", 7),
            ("周3", 3),
            ("星期6", 6),
        ],
    )
    def test_parses(self, text, expected):
        assert parse_weekday(text) == expected

    def test_invalid(self):
        assert parse_weekday("晚上") is None
        assert parse_weekday("第5节") is None


class TestParsePeriods:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("5-6节", (5, 6)),
            ("5-6", (5, 6)),
            ("第3节", (3, 3)),
            ("10-12节", (10, 12)),
        ],
    )
    def test_parses(self, text, expected):
        assert parse_periods(text) == expected

    def test_unsorted(self):
        assert parse_periods("6-5节") == (5, 6)

    def test_invalid(self):
        assert parse_periods("整周") is None


class TestParseWeeks:
    def test_range(self):
        assert parse_weeks("1-8周") == frozenset(range(1, 9))

    def test_full_term(self):
        assert parse_weeks("1-16周") == frozenset(range(1, 17))

    def test_odd_weeks(self):
        # 1-16周(单) = 奇数周
        assert parse_weeks("1-16周(单)") == frozenset(range(1, 17, 2))

    def test_even_weeks(self):
        assert parse_weeks("1-16周(双)") == frozenset(range(2, 17, 2))

    def test_union(self):
        assert parse_weeks("1-8,10-16周") == frozenset(list(range(1, 9)) + list(range(10, 17)))

    def test_full_weeks_keyword(self):
        assert parse_weeks("全周") == DEFAULT_WEEKS

    def test_none_when_no_info(self):
        assert parse_weeks("") is None
        assert parse_weeks("待定") is None


class TestParseMeeting:
    def test_typical(self):
        m = parse_meeting("星期五5-6节(1-8周)")
        assert m is not None
        assert m.weekday == 5
        assert (m.start_period, m.end_period) == (5, 6)
        assert m.weeks == frozenset(range(1, 9))

    def test_default_weeks_full_term(self):
        m = parse_meeting("星期五5-6节")
        assert m is not None
        assert m.weeks == DEFAULT_WEEKS

    def test_invalid(self):
        assert parse_meeting("地点：文体中心") is None


class TestParseTimeRange:
    def test_typical(self):
        tr = parse_time_range("周五5-6")
        assert tr is not None
        assert (tr.weekday, tr.start_period, tr.end_period) == (5, 5, 6)
        assert tr.to_label() == "周五5-6节"

    def test_invalid(self):
        assert parse_time_range("随便写") is None


class TestConflict:
    def test_same_week_weekday_overlap_conflicts(self):
        a = Meeting(weekday=5, start_period=5, end_period=6, weeks=frozenset(range(1, 17)))
        b = Meeting(weekday=5, start_period=5, end_period=6, weeks=frozenset(range(1, 17)))
        assert meetings_conflict(a, b)

    def test_different_weeks_no_conflict(self):
        # 计划 §15 关键用例：1-8周 与 9-16周，星期节次相同也不冲突
        a = Meeting(weekday=5, start_period=5, end_period=6, weeks=frozenset(range(1, 9)))
        b = Meeting(weekday=5, start_period=5, end_period=6, weeks=frozenset(range(9, 17)))
        assert not meetings_conflict(a, b)

    def test_different_weekday_no_conflict(self):
        a = Meeting(weekday=1, start_period=1, end_period=2, weeks=DEFAULT_WEEKS)
        b = Meeting(weekday=2, start_period=1, end_period=2, weeks=DEFAULT_WEEKS)
        assert not meetings_conflict(a, b)

    def test_adjacent_periods_no_conflict(self):
        a = Meeting(weekday=1, start_period=1, end_period=2, weeks=DEFAULT_WEEKS)
        b = Meeting(weekday=1, start_period=3, end_period=4, weeks=DEFAULT_WEEKS)
        assert not meetings_conflict(a, b)

    def test_partial_overlap_conflicts(self):
        a = Meeting(weekday=1, start_period=1, end_period=3, weeks=DEFAULT_WEEKS)
        b = Meeting(weekday=1, start_period=3, end_period=5, weeks=DEFAULT_WEEKS)
        assert meetings_conflict(a, b)

    def test_partial_week_overlap_conflicts(self):
        a = Meeting(weekday=3, start_period=3, end_period=4, weeks=frozenset(range(1, 12)))
        b = Meeting(weekday=3, start_period=3, end_period=4, weeks=frozenset(range(8, 17)))
        assert meetings_conflict(a, b)

    def test_schedule_conflicts_any_pair(self):
        meetings_a = [
            Meeting(weekday=1, start_period=1, end_period=2, weeks=DEFAULT_WEEKS),
            Meeting(weekday=5, start_period=5, end_period=6, weeks=DEFAULT_WEEKS),
        ]
        meetings_b = [
            Meeting(weekday=3, start_period=1, end_period=2, weeks=DEFAULT_WEEKS),
            Meeting(weekday=5, start_period=5, end_period=6, weeks=frozenset(range(1, 9))),
        ]
        assert schedule_conflicts(meetings_a, meetings_b)
        assert not schedule_conflicts(meetings_a, [])

    def test_periods_overlap(self):
        assert periods_overlap(1, 2, 2, 3)
        assert not periods_overlap(1, 2, 3, 4)
