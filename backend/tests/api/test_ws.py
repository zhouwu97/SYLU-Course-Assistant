"""WebSocket 推送与模式 B 确认流程测试。

TestClient 在独立线程跑 ASGI 应用；DB/ watcher 操作统一在同一个 asyncio.run 循环里，
避免跨事件循环使用 aiosqlite 连接。
"""
import asyncio

from fastapi.testclient import TestClient

from app.api.websocket import ConnectionManager
from app.app_state import AppState
from app.domain.course import CourseSection, derive_status
from app.domain.task import EnrollmentState
from app.main import create_app
from app.workers.watcher import Watcher
from tests.api.test_api import FakeAdapter


class TestManager:
    async def test_recent_buffer(self):
        m = ConnectionManager()
        await m.broadcast({"intent_id": "i1", "message": "hello"})
        assert m._recent[-1]["message"] == "hello"
        assert m._recent[-1]["type"] == "event"
        assert m.clients == 0


async def _scenario(tmp_path, body, fn):
    state = AppState(db_path=str(tmp_path / "ws.db"), adapter=FakeAdapter())
    await state.init()
    app = create_app(state)
    try:
        with TestClient(app) as tc:
            # lifespan 已创建并启动 watcher；从 app.state 取同一个实例
            await fn(tc, state, app.state.watcher, body)
    finally:
        watcher = app.state.watcher
        if watcher is not None:
            await watcher.stop()
        await state.close()


async def _create_intent(tc, **extra):
    payload = {
        "course_name": "体育5", "keyword": "羽毛球",
        "preference": {"preferred": {"sections": ["羽毛球5-11"], "teachers": ["孔令宇"]}},
    }
    payload.update(extra)
    return tc.post("/api/intents", json=payload).json()["intent_id"]


class TestWebSocket:
    def test_ws_receives_events(self, tmp_path):
        async def fn(tc, state, watcher, body):
            with tc.websocket_connect("/api/ws") as ws:
                iid = await _create_intent(tc)
                tc.post(f"/api/intents/{iid}/start")  # start 会写事件并广播
                got = ws.receive_json()
                assert got["type"] == "event"

        asyncio.run(_scenario(tmp_path, None, fn))


class TestConfirmFlow:
    def test_confirm_without_pending_returns_409(self, tmp_path):
        async def fn(tc, state, watcher, body):
            iid = await _create_intent(tc)
            r = tc.post(f"/api/intents/{iid}/confirm")
            assert r.status_code == 409

        asyncio.run(_scenario(tmp_path, None, fn))

    def test_decline_returns_waiting(self, tmp_path):
        async def fn(tc, state, watcher, body):
            iid = await _create_intent(tc, mode="confirm")
            intent = await state.db.get_intent(iid)
            intent.state = EnrollmentState.WAITING_CONFIRMATION
            await state.db.upsert_intent(intent)
            watcher._pending_confirmations[iid] = CourseSection(
                jxb_id="jxb-8", jxbmc="羽毛球5-8", kcmc="体育5", teacher_name="孔令宇",
                selected=27, capacity=30, status=derive_status(27, 30),
            )
            r = tc.post(f"/api/intents/{iid}/decline")
            assert r.status_code == 200
            assert r.json()["state"] == "WAITING"

        asyncio.run(_scenario(tmp_path, None, fn))

    def test_confirm_submits_pending(self, tmp_path):
        async def fn(tc, state, watcher, body):
            iid = await _create_intent(tc, mode="confirm")
            intent = await state.db.get_intent(iid)
            intent.state = EnrollmentState.WAITING_CONFIRMATION
            await state.db.upsert_intent(intent)
            watcher._pending_confirmations[iid] = CourseSection(
                jxb_id="jxb-8", jxbmc="羽毛球5-8", kcmc="体育5", teacher_name="孔令宇",
                selected=27, capacity=30, status=derive_status(27, 30),
            )
            r = tc.post(f"/api/intents/{iid}/confirm")
            assert r.status_code == 200
            assert r.json()["section"] == "羽毛球5-8"
            assert r.json()["state"] == "SUCCESS"
            # 事件里应有提交记录
            events = (await state.db.list_events(intent_id=iid))
            assert any("[确认]" in e.message for e in events)

        asyncio.run(_scenario(tmp_path, None, fn))
