// 自动候补（计划 §22、§11、§12）：任务列表 + 确认/放弃 + 引擎控制 + 实时事件
import { useCallback, useEffect, useState } from "react";
import { del, get, post, useEventsWs } from "../api/client";
import {
  CATEGORY_LABELS,
  EngineStatus,
  Intent,
  MODE_LABELS,
  STATE_LABELS,
  TaskEvent,
  fmtTime,
  stateClass,
} from "../types";

export default function Automation() {
  const [intents, setIntents] = useState<Intent[]>([]);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [t, e, s] = await Promise.all([
        get<{ tasks: Intent[] }>("/api/tasks"),
        get<{ events: TaskEvent[] }>("/api/events?limit=30"),
        get<EngineStatus>("/api/status"),
      ]);
      setIntents(t.tasks);
      setEvents(e.events);
      setStatus(s);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEventsWs(
    useCallback((e: TaskEvent) => {
      setEvents((prev) => [e, ...prev].slice(0, 50));
      refresh();
    }, [refresh])
  );

  const act = async (path: string) => {
    try {
      await post(path);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const remove = async (iid: string) => {
    await del(`/api/intents/${iid}`);
    await refresh();
  };

  return (
    <div>
      <h2 style={{ marginBottom: 14 }}>自动候补</h2>
      {error && <div className="error-banner">{error}</div>}

      <div className="card">
        <div className="row between">
          <div>
            自动化引擎：{" "}
            <span className={status?.enginePaused ? "status-wait" : "status-ok"}>
              <span className="status-dot" /> {status?.enginePaused ? "已暂停" : "运行中"}
            </span>
            <span className="muted" style={{ marginLeft: 12 }}>
              最后检查 {fmtTime(status?.lastCheckAt)} · 下次约 {status?.nextCheckInSeconds ?? "-"} 秒
            </span>
          </div>
          <button
            className="btn secondary"
            onClick={() => act(status?.enginePaused ? "/api/engine/resume" : "/api/engine/pause")}
          >
            {status?.enginePaused ? "继续全部" : "暂停全部"}
          </button>
        </div>
      </div>

      {intents.map((it) => (
        <div className="card" key={it.intent_id}>
          <div className="row between">
            <div>
              <strong>{it.course_name || it.keyword}</strong>
              <span className="tag" style={{ marginLeft: 8 }}>{CATEGORY_LABELS[it.category] ?? it.category}</span>
              <span className="tag">{MODE_LABELS[it.mode] ?? it.mode}</span>
              <span className="tag">优先级 {it.priority}</span>
              <span className={`badge ${stateClass(it.state)}`} style={{ marginLeft: 8 }}>
                {STATE_LABELS[it.state] ?? it.state}
              </span>
            </div>
            <div className="row">
              {it.state === "WAITING_CONFIRMATION" && (
                <>
                  <button className="btn" onClick={() => act(`/api/intents/${it.intent_id}/confirm`)}>
                    选这个班
                  </button>
                  <button className="btn secondary" onClick={() => act(`/api/intents/${it.intent_id}/decline`)}>
                    继续等首选
                  </button>
                </>
              )}
              {["IDLE", "PAUSED"].includes(it.state) && (
                <button className="btn" onClick={() => act(`/api/intents/${it.intent_id}/start`)}>
                  启动
                </button>
              )}
              {!["IDLE", "SUCCESS", "PAUSED"].includes(it.state) && (
                <button className="btn secondary" onClick={() => act(`/api/intents/${it.intent_id}/pause`)}>
                  暂停
                </button>
              )}
              <button className="btn danger" onClick={() => remove(it.intent_id)}>
                删除
              </button>
            </div>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            首选：{it.preference.preferred.sections.join("、") || "-"}
            {it.preference.preferred.teachers.length > 0 && ` ｜ 教师 ${it.preference.preferred.teachers.join("、")}`}
            {it.preference.preferred.times.length > 0 && ` ｜ 时间 ${it.preference.preferred.times.join("、")}`}
          </div>
        </div>
      ))}
      {intents.length === 0 && (
        <div className="card muted">还没有选课计划，去"选课计划"页面添加。</div>
      )}

      <div className="card">
        <h2>实时日志（WebSocket 推送）</h2>
        <div className="events">
          {events.length === 0 && <div className="muted">暂无事件</div>}
          {events.map((e) => (
            <div className="event" key={e.event_id}>
              <span className="ts">{fmtTime(e.ts)}</span>
              <span className={`level-${e.level}`}>{e.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
