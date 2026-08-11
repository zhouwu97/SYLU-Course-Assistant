"""课程发现服务测试（计划 §29 分组查询、§3 课程分组）。"""
from app.adapters.zfsoft.enrollment import ZfsoftAdapter
from app.domain.course import CourseSection, SectionStatus
from app.domain.task import CourseIntent
from app.services.course_discovery import (
    CourseDiscoveryService,
    group_queries_by_keyword,
    group_sections_into_courses,
)


def _section(jxbmc="羽毛球5-11", teacher="孔令宇", kcmc="体育5", kch_id="k1",
             selected=29, capacity=30):
    return CourseSection(
        jxb_id=f"jxb-{jxbmc}",
        jxbmc=jxbmc,
        kch_id=kch_id,
        kcmc=kcmc,
        teacher_name=teacher,
        selected=selected,
        capacity=capacity,
        status=SectionStatus.AVAILABLE if selected < capacity else SectionStatus.FULL,
    )


class FakeAdapter:
    def __init__(self, sections_by_keyword: dict[str, list[CourseSection]]):
        self.sections_by_keyword = sections_by_keyword
        self.calls: list[str] = []

    async def list_sections(self, keyword, tab="", course_hint=""):
        self.calls.append(keyword)
        return list(self.sections_by_keyword.get(keyword, []))


class TestGrouping:
    def test_group_sections_into_courses(self):
        sections = [
            _section("羽毛球5-11", "孔令宇", "体育5", "k1"),
            _section("羽毛球5-8", "孔令宇", "体育5", "k1"),
            _section("篮球5-1", "李XX", "体育5", "k2"),
        ]
        courses = group_sections_into_courses(sections, category="sport")
        assert len(courses) == 2
        by_id = {c.kch_id: c for c in courses}
        assert len(by_id["k1"].sections) == 2
        assert by_id["k1"].category == "sport"

    def test_group_queries_by_keyword(self):
        intents = [
            CourseIntent(intent_id="a", keyword="羽毛球"),
            CourseIntent(intent_id="b", keyword="羽毛球"),
            CourseIntent(intent_id="c", keyword="篮球"),
            CourseIntent(intent_id="d", course_name="体育5", keyword=""),
        ]
        groups = group_queries_by_keyword(intents)
        assert list(groups.keys()) == ["羽毛球", "篮球", "体育5"]
        assert len(groups["羽毛球"]) == 2


class TestDiscoveryService:
    async def test_refresh_intents_queries_each_keyword_once(self):
        adapter = FakeAdapter({"羽毛球": [_section()], "篮球": [_section("篮球5-1", "李XX")]})
        svc = CourseDiscoveryService(adapter)
        intents = [
            CourseIntent(intent_id="a", keyword="羽毛球"),
            CourseIntent(intent_id="b", keyword="羽毛球"),
            CourseIntent(intent_id="c", keyword="篮球"),
        ]
        result = await svc.refresh_intents(intents)
        assert adapter.calls == ["羽毛球", "篮球"]
        assert len(result["羽毛球"]) == 1

    async def test_search_courses(self):
        adapter = FakeAdapter({"羽毛球": [_section(), _section("羽毛球5-8")]})
        svc = CourseDiscoveryService(adapter)
        courses = await svc.search_courses("羽毛球", category="sport")
        assert len(courses) == 1
        assert len(courses[0].sections) == 2
