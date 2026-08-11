"""课程 API（计划 §33）：类别 / 课程搜索 / 教学班 / 当前课表。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.app_state import CATEGORIES

router = APIRouter(prefix="/api", tags=["courses"])


@router.get("/course-categories")
async def course_categories() -> dict:
    return {"categories": CATEGORIES}


@router.get("/courses")
async def search_courses(
    request: Request,
    q: str = Query(..., min_length=1, description="课程名称/课程号/教师关键字"),
    category: str = "",
    tab: str = "",
) -> dict:
    """搜索课程并返回全部真实教学班（教师/时间/地点/人数/状态）。"""
    state = request.app.state.app_state
    discovery = await state.discovery()
    courses = await discovery.search_courses(q, tab=tab, category=category)
    return {"courses": [c.to_dict() for c in courses]}


@router.get("/courses/{course_id}/sections")
async def course_sections(
    request: Request,
    course_id: str,
    q: str = Query(..., description="搜索关键词"),
    tab: str = "",
) -> dict:
    """按课程 kch_id 过滤教学班。"""
    state = request.app.state.app_state
    discovery = await state.discovery()
    courses = await discovery.search_courses(q, tab=tab)
    for c in courses:
        if c.kch_id == course_id or c.kch == course_id:
            return {"course": c.to_dict()}
    raise HTTPException(status_code=404, detail=f"未找到课程 {course_id}")


@router.get("/schedule/current")
async def current_schedule(request: Request) -> dict:
    """当前已选课表（Meeting 列表），用于冲突判断。"""
    state = request.app.state.app_state
    adapter = await state.get_adapter()
    meetings = await adapter.get_my_schedule()
    return {
        "meetings": [
            {
                "weekday": m.weekday,
                "start_period": m.start_period,
                "end_period": m.end_period,
                "weeks": sorted(m.weeks),
                "place": m.place,
            }
            for m in meetings
        ]
    }
