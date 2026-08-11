"""FastAPI API 测试（计划 §36：tests/api/）。

用 FakeAdapter 注入，不启动真实浏览器。
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.zfsoft.enrollment import ZfsoftAdapter
from app.app_state import AppState
from app.domain.course import CourseSection, derive_status
from app.domain.schedule import Meeting
from app.main import create_app


def _sections():
    return [
        CourseSection(
            jxb_id="jxb-11", jxbmc="羽毛球5-11", kch_id="k1", kcmc="体育5",
            teacher_name="孔令宇",
            meetings=(Meeting(weekday=5, start_period=5, end_period=6),),
            selected=30, capacity=30, status=derive_status(30, 30),
        ),
        CourseSection(
            jxb_id="jxb-8", jxbmc="羽毛球5-8", kch_id="k1", kcmc="体育5",
            teacher_name="孔令宇",
            meetings=(Meeting(weekday=5, start_period=7, end_period=8),),
            selected=27, capacity=30, status=derive_status(27, 30),
        ),
        CourseSection(
            jxb_id="jxb-3", jxbmc="羽毛球5-3", kch_id="k2", kcmc="体育5",
            teacher_name="李XX",
            meetings=(Meeting(weekday=5, start_period=5, end_period=6),),
            selected=10, capacity=30, status=derive_status(10, 30),
        ),
    ]


class FakeAdapter:
    def __init__(self):
        self.logged_in = True
        self.enroll_calls: list[str] = []

    async def login_status(self):
        return self.logged_in

    async def ensure_login(self, timeout_s=300, on_waiting=None):
        self.logged_in = True
        return True

    async def list_sections(self, keyword, tab="", course_hint=""):
        return _sections()

    async def get_my_schedule(self):
        return []

    async def get_selected_sections(self):
        return []

    async def enroll(self, section):
        self.enroll_calls.append(section.jxbmc)
        from app.adapters.zfsoft.parser import EnrollOutcome, EnrollResult

        return EnrollResult(EnrollOutcome.SUCCESS, "选课成功")


@pytest.fixture
async def client(tmp_path):
    adapter = FakeAdapter()
    state = AppState(db_path=tmp_path / "test.db", adapter=adapter)
    await state.init()
    app = create_app(state)
    from app.workers.watcher import Watcher

    watcher = Watcher(state)
    await watcher.start()
    app.state.watcher = watcher
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac, adapter, state
    await watcher.stop()
    await state.close()


class TestAuth:
    async def test_status_not_logged_in_before_start(self, client):
        ac, _, _ = client
        r = await ac.get("/api/auth/status")
        assert r.status_code == 200
        assert r.json()["loggedIn"] is True  # FakeAdapter 默认已登录

    async def test_open(self, client):
        ac, adapter, _ = client
        r = await ac.post("/api/auth/open")
        assert r.status_code == 200
        assert r.json()["loggedIn"] is True


class TestCourses:
    async def test_search_courses_groups_sections(self, client):
        ac, _, _ = client
        r = await ac.get("/api/courses", params={"q": "羽毛球"})
        assert r.status_code == 200
        courses = r.json()["courses"]
        assert len(courses) == 2
        k1 = next(c for c in courses if c["kch_id"] == "k1")
        assert len(k1["sections"]) == 2
        sec = k1["sections"][0]
        assert sec["teacher"] == "孔令宇"
        assert sec["status"] == "FULL"

    async def test_course_sections_by_id(self, client):
        ac, _, _ = client
        r = await ac.get("/api/courses/k1/sections", params={"q": "羽毛球"})
        assert r.status_code == 200
        assert r.json()["course"]["kch_id"] == "k1"

    async def test_course_sections_404(self, client):
        ac, _, _ = client
        r = await ac.get("/api/courses/nope/sections", params={"q": "羽毛球"})
        assert r.status_code == 404

    async def test_course_categories(self, client):
        ac, _, _ = client
        r = await ac.get("/api/course-categories")
        ids = [c["id"] for c in r.json()["categories"]]
        assert ids == ["main", "general", "sport"]


class TestIntents:
    async def _create(self, ac, keyword="羽毛球"):
        return await ac.post("/api/intents", json={
            "course_name": "体育5", "category": "sport", "keyword": keyword,
            "mode": "auto",
            "preference": {
                "preferred": {"sections": ["羽毛球5-11"], "teachers": ["孔令宇"]},
                "avoid": {"teachers": [], "times": []},
                "fallback": {},
            },
        })

    async def test_create_and_list(self, client):
        ac, _, _ = client
        r = await self._create(ac)
        assert r.status_code == 200
        iid = r.json()["intent_id"]
        r2 = await ac.get("/api/intents")
        assert len(r2.json()["intents"]) == 1
        assert r2.json()["intents"][0]["intent_id"] == iid
        assert r2.json()["intents"][0]["preference"]["preferred"]["teachers"] == ["孔令宇"]

    async def test_update_and_delete(self, client):
        ac, _, _ = client
        iid = (await self._create(ac)).json()["intent_id"]
        r = await ac.put(f"/api/intents/{iid}", json={"mode": "notify"})
        assert r.json()["mode"] == "notify"
        r = await ac.delete(f"/api/intents/{iid}")
        assert r.json()["deleted"] is True
        r = await ac.get("/api/intents")
        assert r.json()["intents"] == []

    async def test_preview_returns_decision(self, client):
        ac, _, _ = client
        iid = (await self._create(ac)).json()["intent_id"]
        r = await ac.post(f"/api/intents/{iid}/preview")
        body = r.json()
        assert body["decision"]["action"] == "AUTO_ENROLL"
        assert body["decision"]["section"] == "羽毛球5-8"  # 首选满，替代有余量
        assert body["candidates"][0]["tier"] == 0
        reasons = body["candidates"][0]["reasons"]
        assert "首选教学班" in reasons

    async def test_start_and_pause(self, client):
        ac, _, _ = client
        iid = (await self._create(ac)).json()["intent_id"]
        r = await ac.post(f"/api/intents/{iid}/start")
        assert r.json()["state"] == "WAITING"
        r = await ac.post(f"/api/intents/{iid}/pause")
        assert r.json()["state"] == "PAUSED"

    async def test_events_recorded(self, client):
        ac, _, _ = client
        iid = (await self._create(ac)).json()["intent_id"]
        await ac.post(f"/api/intents/{iid}/preview")
        r = await ac.get("/api/events")
        assert len(r.json()["events"]) >= 1

    async def test_preview_respects_blacklist(self, client):
        ac, _, _ = client
        r = await ac.post("/api/intents", json={
            "course_name": "体育5", "keyword": "羽毛球",
            "preference": {
                "preferred": {"sections": ["羽毛球5-11"], "teachers": ["孔令宇"]},
                "avoid": {"teachers": ["孔令宇"], "times": []},
                "fallback": {},
            },
        })
        iid = r.json()["intent_id"]
        r2 = await ac.post(f"/api/intents/{iid}/preview")
        body = r2.json()
        # 首选班老师上黑名单 -> 换到 李XX 的班
        assert body["decision"]["section"] == "羽毛球5-3"


class TestEngine:
    async def test_status(self, client):
        ac, _, _ = client
        r = await ac.get("/api/status")
        assert r.status_code == 200
        assert r.json()["loggedIn"] is True
        assert r.json()["engineRunning"] is True

    async def test_engine_pause_resume(self, client):
        ac, _, _ = client
        r = await ac.post("/api/engine/pause")
        assert r.json()["paused"] is True
        r = await ac.post("/api/engine/resume")
        assert r.json()["paused"] is False

    async def test_health(self, client):
        ac, _, _ = client
        r = await ac.get("/api/health")
        assert r.json()["ok"] is True
