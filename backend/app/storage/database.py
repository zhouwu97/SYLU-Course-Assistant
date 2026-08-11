"""SQLite 持久化（计划 §27）。

只存用户选课计划与偏好，绝不存 Cookie/JSESSIONID（计划 §32）。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from app.domain.task import CourseIntent, TaskEvent, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS course_intents (
    intent_id        TEXT PRIMARY KEY,
    course_id        TEXT DEFAULT '',
    course_name      TEXT DEFAULT '',
    category         TEXT DEFAULT '',
    keyword          TEXT DEFAULT '',
    priority         INTEGER DEFAULT 100,
    mode             TEXT DEFAULT 'confirm',
    state            TEXT DEFAULT 'IDLE',
    preference_json  TEXT NOT NULL DEFAULT '{}',
    schedule_json    TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_events (
    event_id   TEXT PRIMARY KEY,
    intent_id  TEXT NOT NULL,
    ts         TEXT NOT NULL,
    level      TEXT NOT NULL DEFAULT 'info',
    message    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS app_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_events_intent ON task_events(intent_id, ts);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn: aiosqlite.Connection | None = None
        self._ready = False

    async def init(self) -> None:
        await self._ensure_conn()

    async def _ensure_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self.path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.executescript(_SCHEMA)
            await self._conn.commit()
            self._ready = True
        return self._conn

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ---- course_intents ---------------------------------------------------

    async def upsert_intent(self, intent: CourseIntent) -> None:
        conn = await self._ensure_conn()
        await conn.execute(
            """INSERT INTO course_intents
               (intent_id, course_id, course_name, category, keyword, priority,
                mode, state, preference_json, schedule_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(intent_id) DO UPDATE SET
                 course_id=excluded.course_id,
                 course_name=excluded.course_name,
                 category=excluded.category,
                 keyword=excluded.keyword,
                 priority=excluded.priority,
                 mode=excluded.mode,
                 state=excluded.state,
                 preference_json=excluded.preference_json,
                 schedule_json=excluded.schedule_json,
                 updated_at=excluded.updated_at""",
            (
                intent.intent_id,
                intent.course_id,
                intent.course_name,
                intent.category,
                intent.keyword,
                intent.priority,
                intent.mode.value,
                intent.state.value,
                json.dumps(intent.preference.to_dict(), ensure_ascii=False),
                json.dumps(
                    [
                        {"weekday": m.weekday, "start_period": m.start_period,
                         "end_period": m.end_period, "weeks": sorted(m.weeks), "place": m.place}
                        for m in intent.existing_schedule
                    ],
                    ensure_ascii=False,
                ),
                intent.created_at,
                intent.updated_at,
            ),
        )
        await conn.commit()

    async def list_intents(self) -> list[CourseIntent]:
        conn = await self._ensure_conn()
        cur = await conn.execute(
            "SELECT * FROM course_intents ORDER BY priority, created_at"
        )
        rows = await cur.fetchall()
        return [self._row_to_intent(r) for r in rows]

    async def get_intent(self, intent_id: str) -> CourseIntent | None:
        conn = await self._ensure_conn()
        cur = await conn.execute(
            "SELECT * FROM course_intents WHERE intent_id = ?", (intent_id,)
        )
        row = await cur.fetchone()
        return self._row_to_intent(row) if row else None

    async def delete_intent(self, intent_id: str) -> bool:
        conn = await self._ensure_conn()
        cur = await conn.execute(
            "DELETE FROM course_intents WHERE intent_id = ?", (intent_id,)
        )
        await conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _row_to_intent(row: aiosqlite.Row) -> CourseIntent:
        from app.domain.preference import CoursePreference
        from app.domain.schedule import Meeting
        from app.domain.task import AutomationMode, EnrollmentState

        d = dict(row)
        schedule = json.loads(d["schedule_json"])
        meetings = [
            Meeting(
                weekday=int(m["weekday"]),
                start_period=int(m["start_period"]),
                end_period=int(m["end_period"]),
                weeks=frozenset(m.get("weeks") or range(1, 17)),
                place=str(m.get("place") or ""),
            )
            for m in schedule
        ]
        return CourseIntent(
            intent_id=d["intent_id"],
            course_id=d["course_id"],
            course_name=d["course_name"],
            category=d["category"],
            keyword=d["keyword"],
            priority=int(d["priority"]),
            mode=AutomationMode(d["mode"]),
            state=EnrollmentState(d["state"]),
            preference=CoursePreference.from_dict(json.loads(d["preference_json"])),
            existing_schedule=meetings,
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )

    # ---- task_events ------------------------------------------------------

    async def add_event(self, intent_id: str, message: str, level: str = "info") -> TaskEvent:
        conn = await self._ensure_conn()
        event = TaskEvent(
            event_id=uuid.uuid4().hex[:12],
            intent_id=intent_id,
            ts=utc_now(),
            level=level,
            message=message,
        )
        await self._conn.execute(
            "INSERT INTO task_events (event_id, intent_id, ts, level, message) VALUES (?, ?, ?, ?, ?)",
            (event.event_id, event.intent_id, event.ts, event.level, event.message),
        )
        await conn.commit()
        return event

    async def list_events(self, intent_id: str | None = None, limit: int = 100) -> list[TaskEvent]:
        conn = await self._ensure_conn()
        if intent_id:
            cur = await conn.execute(
                "SELECT * FROM task_events WHERE intent_id = ? ORDER BY ts DESC LIMIT ?",
                (intent_id, limit),
            )
        else:
            cur = await conn.execute(
                "SELECT * FROM task_events ORDER BY ts DESC LIMIT ?", (limit,)
            )
        rows = await cur.fetchall()
        return [
            TaskEvent(event_id=r["event_id"], intent_id=r["intent_id"], ts=r["ts"],
                      level=r["level"], message=r["message"])
            for r in rows
        ]

    # ---- app_settings -----------------------------------------------------

    async def get_setting(self, key: str) -> str | None:
        conn = await self._ensure_conn()
        cur = await conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        conn = await self._ensure_conn()
        await conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await conn.commit()
