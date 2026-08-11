"""选课计划 API（计划 §13、§24、§33）：CourseIntent CRUD + 决策预览 + 启停。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.websocket import manager as ws_manager
from app.domain.task import AutomationMode, CourseIntent, EnrollmentState, utc_now
from app.services.ranking import decide

router = APIRouter(prefix="/api/intents", tags=["plans"])


class IntentCreate(BaseModel):
    course_id: str = ""
    course_name: str = ""
    category: str = ""
    keyword: str = Field(..., min_length=1, description="搜索关键词，如 羽毛球")
    priority: int = 100
    mode: str = "confirm"
    preference: dict = Field(default_factory=dict)
    existing_schedule: list[dict] = Field(default_factory=list)


class IntentUpdate(BaseModel):
    priority: int | None = None
    mode: str | None = None
    preference: dict | None = None
    existing_schedule: list[dict] | None = None


@router.post("")
async def create_intent(request: Request, body: IntentCreate) -> dict:
    state = request.app.state.app_state
    intent = CourseIntent(
        intent_id=uuid.uuid4().hex[:12],
        course_id=body.course_id,
        course_name=body.course_name,
        category=body.category,
        keyword=body.keyword,
        priority=body.priority,
        mode=AutomationMode(body.mode),
        state=EnrollmentState.IDLE,
    )
    intent.preference = intent.preference.from_dict(body.preference)
    intent.existing_schedule = _meetings_from_payload(body.existing_schedule)
    await state.db.upsert_intent(intent)
    return intent.to_dict()


@router.get("")
async def list_intents(request: Request) -> dict:
    state = request.app.state.app_state
    intents = await state.db.list_intents()
    return {"intents": [i.to_dict() for i in intents]}


@router.put("/{intent_id}")
async def update_intent(request: Request, intent_id: str, body: IntentUpdate) -> dict:
    state = request.app.state.app_state
    intent = await state.db.get_intent(intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="意图不存在")
    if body.priority is not None:
        intent.priority = body.priority
    if body.mode is not None:
        intent.mode = AutomationMode(body.mode)
    if body.preference is not None:
        intent.preference = intent.preference.from_dict(body.preference)
    if body.existing_schedule is not None:
        intent.existing_schedule = _meetings_from_payload(body.existing_schedule)
    intent.updated_at = utc_now()
    await state.db.upsert_intent(intent)
    return intent.to_dict()


@router.delete("/{intent_id}")
async def delete_intent(request: Request, intent_id: str) -> dict:
    state = request.app.state.app_state
    ok = await state.db.delete_intent(intent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="意图不存在")
    return {"deleted": True}


@router.post("/{intent_id}/preview")
async def preview_intent(request: Request, intent_id: str) -> dict:
    """决策预览（计划 §24）：按当前规则评估，明确显示程序会选哪个班。"""
    state = request.app.state.app_state
    intent = await state.db.get_intent(intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="意图不存在")
    discovery = await state.discovery()
    sections = await discovery.search_sections(intent.keyword, tab=_tab_for(intent))
    decision = decide(sections, intent)
    await _log_and_broadcast(state, intent_id, f"决策预览：{decision.message}")
    return decision.to_dict()


@router.post("/{intent_id}/start")
async def start_intent(request: Request, intent_id: str) -> dict:
    state = request.app.state.app_state
    intent = await state.db.get_intent(intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="意图不存在")
    intent.state = EnrollmentState.WAITING
    intent.updated_at = utc_now()
    await state.db.upsert_intent(intent)
    await _log_and_broadcast(state, intent_id, "任务启动，进入候补监测", level="success")
    return intent.to_dict()


@router.post("/{intent_id}/pause")
async def pause_intent(request: Request, intent_id: str) -> dict:
    state = request.app.state.app_state
    intent = await state.db.get_intent(intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="意图不存在")
    intent.state = EnrollmentState.PAUSED
    intent.updated_at = utc_now()
    await state.db.upsert_intent(intent)
    await _log_and_broadcast(state, intent_id, "任务暂停", level="warn")
    return intent.to_dict()


@router.post("/{intent_id}/confirm")
async def confirm_intent(request: Request, intent_id: str) -> dict:
    """模式 B：用户确认后提交待确认教学班（计划 §11、§12）。"""
    state = request.app.state.app_state
    watcher = request.app.state.watcher
    intent = await state.db.get_intent(intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="意图不存在")
    if watcher is None:
        raise HTTPException(status_code=409, detail="引擎未运行")
    section = await watcher.submit_pending(intent)
    if section is None:
        raise HTTPException(status_code=409, detail="当前没有待确认的教学班")
    return {"confirmed": True, "section": section.jxbmc, "state": intent.state.value}


@router.post("/{intent_id}/decline")
async def decline_intent(request: Request, intent_id: str) -> dict:
    """模式 B：放弃替代班，继续等首选。"""
    state = request.app.state.app_state
    watcher = request.app.state.watcher
    intent = await state.db.get_intent(intent_id)
    if intent is None:
        raise HTTPException(status_code=404, detail="意图不存在")
    declined = bool(watcher and watcher.decline_pending(intent_id))
    if intent.state == EnrollmentState.WAITING_CONFIRMATION:
        intent.state = EnrollmentState.WAITING
        intent.updated_at = utc_now()
        await state.db.upsert_intent(intent)
    await _log_and_broadcast(state, intent_id, "已放弃替代班，继续等待首选", level="info")
    return {"declined": declined, "state": intent.state.value}


def _tab_for(intent: CourseIntent) -> str:
    return {"main": "主修课程", "general": "通识选修课", "sport": "体育分项"}.get(intent.category, "")


async def _log_and_broadcast(state, intent_id: str, message: str, level: str = "info") -> None:
    """写事件日志并通过 WebSocket 实时推送（计划 §21、§23）。"""
    from app.api.websocket import manager as ws_manager

    event = await state.db.add_event(intent_id, message, level)
    await ws_manager.broadcast(event.to_dict())


def _meetings_from_payload(payload: list[dict]):
    from app.domain.schedule import Meeting

    meetings = []
    for m in payload or []:
        meetings.append(
            Meeting(
                weekday=int(m["weekday"]),
                start_period=int(m["start_period"]),
                end_period=int(m["end_period"]),
                weeks=frozenset(m.get("weeks") or range(1, 17)),
                place=str(m.get("place") or ""),
            )
        )
    return meetings
