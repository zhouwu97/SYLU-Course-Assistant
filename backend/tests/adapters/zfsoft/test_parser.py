"""zfsoft 解析器测试：JSON items、DOM 行、文本块、提交结果分类（计划 §36）。"""
import pytest

from app.adapters.zfsoft.parser import (
    EnrollOutcome,
    classify_enroll_result,
    parse_section_from_text,
    parse_sections_from_dom_rows,
    parse_sections_from_items,
)


class TestParseItems:
    """基于用户抓包字段（jxb_id/jxbmc/kch/kch_id/kcmc/yxzrs）的真实结构。"""

    def _item(self, **overrides):
        row = {
            "jxb_id": "2026-2027-1-0110010023-0001",
            "jxbmc": "羽毛球5-11",
            "kch": "211700013",
            "kch_id": "211700013-01",
            "kcmc": "体育5",
            "rkjs": "孔令宇",
            "skdd": "文体中心B馆",
            "skxq": "星期五",
            "skjc": "5-6节",
            "skzc": "1-16周",
            "sxr": "29",
            "yxzrs": "30",
        }
        row.update(overrides)
        return row

    def test_parses_all_fields(self):
        sections = parse_sections_from_items([self._item()])
        assert len(sections) == 1
        s = sections[0]
        assert s.jxb_id == "2026-2027-1-0110010023-0001"
        assert s.jxbmc == "羽毛球5-11"
        assert s.kcmc == "体育5"
        assert s.teacher_name == "孔令宇"
        assert s.place == "文体中心B馆"
        assert (s.selected, s.capacity) == (29, 30)
        assert s.status.value == "AVAILABLE"
        assert len(s.meetings) == 1
        m = s.meetings[0]
        assert (m.weekday, m.start_period, m.end_period) == (5, 5, 6)
        assert m.weeks == frozenset(range(1, 17))

    def test_full_section_derives_full_status(self):
        sections = parse_sections_from_items([self._item(sxr="30")])
        assert sections[0].status.value == "FULL"

    def test_multiple_meeting_rows_merged_by_jxb_id(self):
        rows = [
            self._item(skjc="5-6节", skxq="星期三"),
            self._item(skjc="3-4节", skxq="星期五"),
        ]
        sections = parse_sections_from_items(rows)
        assert len(sections) == 1
        assert len(sections[0].meetings) == 2

    def test_combined_skjc_with_weekday_and_weeks(self):
        row = self._item(skxq="", skjc="星期五5-6节{1-8周}", skzc="")
        sections = parse_sections_from_items([row])
        s = sections[0]
        assert len(s.meetings) == 1
        assert s.meetings[0].weeks == frozenset(range(1, 9))

    def test_unknown_capacity(self):
        sections = parse_sections_from_items([self._item(sxr="", yxzrs="")])
        assert sections[0].status.value == "UNKNOWN"

    def test_single_week(self):
        row = self._item(skjc="第5节", skxq="星期一", skzc="3周")
        sections = parse_sections_from_items([row])
        assert sections[0].meetings[0].weeks == frozenset({3})


class TestDomRows:
    def test_parses_row(self):
        rows = [
            ["体育5", "羽毛球5-11", "孔令宇", "星期五 5-6节(1-16周)", "文体中心B馆", "29", "30", "选课"],
        ]
        sections = parse_sections_from_dom_rows(rows, course_hint="体育5")
        assert len(sections) == 1
        s = sections[0]
        assert s.jxbmc == "羽毛球5-11"
        assert s.teacher_name == "孔令宇"
        assert (s.selected, s.capacity) == (29, 30)
        assert s.status.value == "AVAILABLE"
        assert s.kcmc == "体育5"

    def test_skips_rows_without_jxbmc(self):
        rows = [["标题行", "没有教学班"], ["体育5", "羽毛球5-11", "孔令宇", "星期五5-6节", "29/30", "选课"]]
        sections = parse_sections_from_dom_rows(rows)
        assert len(sections) == 1

    def test_slash_capacity_cell(self):
        rows = [["体育5", "羽毛球5-8", "孔令宇", "周五5-6", "27/30", "选课"]]
        sections = parse_sections_from_dom_rows(rows)
        assert (sections[0].selected, sections[0].capacity) == (27, 30)

    def test_full_cell(self):
        rows = [["体育5", "羽毛球5-12", "李XX", "周五7-8", "30/30", "选课"]]
        assert parse_sections_from_dom_rows(rows)[0].status.value == "FULL"


class TestTextBlob:
    def test_parses_blob(self):
        blob = "体育5 羽毛球5-11 孔令宇 星期五5-6节(1-16周) 文体中心B馆 29/30 选课"
        s = parse_section_from_text(blob, course_hint="体育5")
        assert s is not None
        assert s.jxbmc == "羽毛球5-11"
        assert s.teacher_name == "孔令宇"
        assert (s.selected, s.capacity) == (29, 30)
        assert len(s.meetings) == 1

    def test_none_without_jxbmc(self):
        assert parse_section_from_text("体育5 人数已满 选课") is None

    def test_full(self):
        s = parse_section_from_text("羽毛球5-12 李XX 星期五7-8 30/30 选课")
        assert s is not None
        assert s.status.value == "FULL"


class TestClassify:
    def test_success(self):
        r = classify_enroll_result({"flag": "1", "msg": "选课成功"})
        assert r.outcome == EnrollOutcome.SUCCESS
        assert r.ok and r.is_section_level is False

    def test_full(self):
        r = classify_enroll_result({"msg": "人数已满"})
        assert r.outcome == EnrollOutcome.FULL
        assert r.is_section_level is True

    def test_conflict(self):
        r = classify_enroll_result({"msg": "上课时间冲突"})
        assert r.outcome == EnrollOutcome.CONFLICT
        assert r.is_section_level is True

    def test_rejected_section_level(self):
        r = classify_enroll_result({"msg": "超过选课人数上限"})
        assert r.outcome == EnrollOutcome.REJECTED
        assert r.is_section_level is True

    def test_rejected_course_level_qualification(self):
        r = classify_enroll_result({"msg": "不符合课程选修资格限制"})
        assert r.outcome == EnrollOutcome.REJECTED
        assert r.is_section_level is False

    def test_session_expired_from_page_text(self):
        r = classify_enroll_result({}, page_text="登录已失效，请重新登录")
        assert r.outcome == EnrollOutcome.SESSION_EXPIRED

    def test_network(self):
        r = classify_enroll_result({"msg": "系统繁忙，请稍后重试"})
        assert r.outcome == EnrollOutcome.NETWORK_ERROR

    def test_unknown(self):
        r = classify_enroll_result({"msg": "未知返回码 10086"})
        assert r.outcome == EnrollOutcome.UNKNOWN
