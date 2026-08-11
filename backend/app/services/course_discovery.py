"""课程发现服务（计划 §3、§二十九）。

用户只输入关键词，系统返回该课程全部真实教学班（教师/时间/地点/人数/状态）。
监测任务按查询分组：同一关键词一次查询，同时评估所有相关意图。
"""
from __future__ import annotations

from collections import OrderedDict

from app.adapters.zfsoft.enrollment import ZfsoftAdapter
from app.domain.course import Course, CourseSection
from app.domain.task import CourseIntent


def group_sections_into_courses(
    sections: list[CourseSection], category: str = ""
) -> list[Course]:
    """把教学班按课程分组（kch_id 优先，回退课程名）。"""
    grouped: OrderedDict[str, list[CourseSection]] = OrderedDict()
    for s in sections:
        key = s.kch_id or s.kcmc or "未知课程"
        grouped.setdefault(key, []).append(s)
    courses: list[Course] = []
    for key, secs in grouped.items():
        first = secs[0]
        courses.append(
            Course(
                kch_id=first.kch_id or key,
                kch=first.kch,
                name=first.kcmc or key,
                category=category,
                sections=secs,
            )
        )
    return courses


def group_queries_by_keyword(intents: list[CourseIntent]) -> dict[str, list[CourseIntent]]:
    """计划 §29：按查询关键词分组，同一关键词只查询一次。"""
    groups: OrderedDict[str, list[CourseIntent]] = OrderedDict()
    for intent in intents:
        key = (intent.keyword or intent.course_name or "").strip()
        if not key:
            continue
        groups.setdefault(key, []).append(intent)
    return groups


class CourseDiscoveryService:
    """课程/教学班发现。只依赖 ZfsoftAdapter，业务层不碰页面。"""

    def __init__(self, adapter: ZfsoftAdapter):
        self.adapter = adapter

    async def search_courses(self, keyword: str, tab: str = "", category: str = "") -> list[Course]:
        sections = await self.adapter.list_sections(keyword, tab=tab, course_hint=keyword)
        return group_sections_into_courses(sections, category=category)

    async def search_sections(self, keyword: str, tab: str = "") -> list[CourseSection]:
        return await self.adapter.list_sections(keyword, tab=tab, course_hint=keyword)

    async def refresh_intents(self, intents: list[CourseIntent], tab: str = "") -> dict[str, list[CourseSection]]:
        """按关键词分组刷新：每个关键词一次查询，返回 关键词 -> 教学班列表。"""
        result: dict[str, list[CourseSection]] = {}
        for keyword, group in group_queries_by_keyword(intents).items():
            sections = await self.adapter.list_sections(keyword, tab=tab, course_hint=keyword)
            result[keyword] = sections
        return result
