// 总览（计划 §3 首页）：登录状态 / 引擎状态 / 活动任务 / 实时日志
import { useCallback, useEffect, useState } from "react";
import { get, post, useEventsWs } from "../api/client";
import {
  EngineStatus,
  TaskEvent,
  fmtTime,
} from "../types";

export default function Dashboard() {
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await get<EngineStatus>("/api/status"));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const refreshEvents = useCallback(async () => {
    try {
      setEvents(await get<{ events: TaskEvent[] }>("/api/events?limit=25").then((r) => r.events));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshEvents();
    const t = setInterval(refreshStatus, 5000);
    return () => clearInterval(t);
  }, [refreshStatus, refreshEvents]);

  useEventsWs(
    useCallback((e: TaskEvent) => {
      setEvents((prev) => [e, ...prev].slice(0, 50));
    }, [])
  );

  const openLogin = async () => {
    setBusy(true);
    setError("");
    try {
      await post("/api/auth/open");
      await refreshStatus();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const toggleEngine = async () => {
    await post(status?.enginePaused ? "/api/engine/resume" : "/api/engine/pause");
    await refreshStatus();
  };

  return (
    <div>
      <h2 style={{ marginBottom: 14 }}>选课控制台</h2>
      {error && <div className="error-banner">{error}</div>}

      <div className="row" style={{ marginBottom: 16 }}>
        <div className="card" style={{ flex: 1 }}>
          <h2>
            登录状态{" "}
            <span className={status?.loggedIn ? "status-ok" : "status-full"}>
              <span className="status-dot" /> {status?.loggedIn ? "已登录" : "未登录"}
            </span>
          </h2>
          {!status?.loggedIn && (
            <button className="btn" onClick={openLogin} disabled={busy}>
              {busy ? "等待登录..." : "打开教务登录"}
            </button>
          )}
          <p className="muted" style={{ marginTop: 8 }}>
            登录态只保存在本地浏览器 profile，不会写入数据库或日志。
          </p>
        </div>

        <div className="card" style={{ flex: 1 }}>
          <h2>
            自动化引擎{" "}
            <span className={status?.enginePaused ? "status-wait" : "status-ok"}>
              <span className="status-dot" /> {status?.enginePaused ? "已暂停" : "运行中"}
            </span>
          </h2>
          <div className="muted" style={{ marginBottom: 10 }}>
            最后检查：{fmtTime(status?.lastCheckAt)}　下次检查：约 {status?.nextCheckInSeconds ?? "-"} 秒后
            <br />
            活动任务：{status?.activeTasks ?? 0}
          </div>
          <button className="btn secondary" onClick={toggleEngine}>
            {status?.enginePaused ? "继续全部" : "暂停全部"}
          </button>
        </div>
      </div>

      <div className="card">
        <h2>最近日志</h2>
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
