"""领域模型基础测试：教学班状态推导、偏好序列化、意图序列化。"""
import pytest

from app.domain.course import CourseSection, SectionStatus, derive_status
from app.domain.preference import CoursePreference
from app.domain.schedule import Meeting
from app.domain.task import AutomationMode, CourseIntent, EnrollmentState


class TestSectionStatus:
    def test_available(self):
        assert derive_status(29, 30) == SectionStatus.AVAILABLE

    def test_full(self):
        assert derive_status(30, 30) == SectionStatus.FULL

    def test_unknown(self):
        assert derive_status(None, 30) == SectionStatus.UNKNOWN
        assert derive_status(29, None) == SectionStatus.UNKNOWN

    def test_properties(self):
        s = CourseSection(jxb_id="x1", jxbmc="羽毛球5-11", selected=29, capacity=30,
                          status=derive_status(29, 30))
        assert s.has_seat and not s.is_full
        assert s.availability_text == "29/30"

    def test_conflict_with_schedule(self):
        s = CourseSection(
            jxb_id="x1", jxbmc="羽毛球5-11",
            meetings=(Meeting(weekday=5, start_period=5, end_period=6),),
        )
        assert s.conflicts_with([Meeting(weekday=5, start_period=5, end_period=6)])
        assert not s.conflicts_with([Meeting(weekday=1, start_period=1, end_period=2)])


class TestPreferenceRoundtrip:
    def test_to_dict_from_dict(self):
        pref = CoursePreference(
            preferred_sections=["羽毛球5-11"],
            preferred_teachers=["孔令宇"],
            avoided_teachers=["王XX"],
            allow_other_teacher=True,
            allow_other_time=False,
        )
        d = pref.to_dict()
        assert d["preferred"]["times"] == []
        assert d["avoid"]["times"] == []

        restored = CoursePreference.from_dict(d)
        assert restored.preferred_sections == ["羽毛球5-11"]
        assert restored.preferred_teachers == ["孔令宇"]
        assert restored.avoided_teachers == ["王XX"]
        assert restored.allow_other_teacher is True
        assert restored.allow_other_time is False

    def test_times_roundtrip(self):
        from app.domain.schedule import parse_time_range

        pref = CoursePreference(preferred_times=[parse_time_range("周五5-6")])
        restored = CoursePreference.from_dict(pref.to_dict())
        assert len(restored.preferred_times) == 1
        assert (restored.preferred_times[0].weekday, restored.preferred_times[0].start_period) == (5, 5)


class TestIntentRoundtrip:
    def test_roundtrip(self):
        intent = CourseIntent(
            intent_id="i1",
            course_id="211700013",
            course_name="体育5",
            keyword="羽毛球",
            category="sport",
            mode=AutomationMode.CONFIRM,
            state=EnrollmentState.WAITING,
            existing_schedule=[Meeting(weekday=1, start_period=1, end_period=2)],
        )
        d = intent.to_dict()
        restored = CourseIntent.from_dict(d)
        assert restored.intent_id == "i1"
        assert restored.mode == AutomationMode.CONFIRM
        assert restored.state == EnrollmentState.WAITING
        assert len(restored.existing_schedule) == 1
        assert restored.existing_schedule[0].weekday == 1

    def test_default_mode_is_confirm(self):
        assert CourseIntent(intent_id="i").mode == AutomationMode.CONFIRM
