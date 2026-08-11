// 设置（计划 §30）：监测间隔 / 浏览器 / 安全说明
import { useEffect, useState } from "react";
import { get, put } from "../api/client";
import { SettingsData } from "../types";

export default function Settings() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [intervalMin, setIntervalMin] = useState("8");
  const [intervalMax, setIntervalMax] = useState("15");
  const [channel, setChannel] = useState("edge");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    get<{ settings: SettingsData }>("/api/settings")
      .then((r) => {
        const s = r.settings;
        setSettings(s);
        setIntervalMin(String(s.interval_min));
        setIntervalMax(String(s.interval_max));
        setChannel(s.browser_channel);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const save = async () => {
    setError("");
    try {
      const r = await put<{ settings: SettingsData }>("/api/settings", {
        interval_min: Number(intervalMin),
        interval_max: Number(intervalMax),
        browser_channel: channel,
      });
      setSettings(r.settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: 14 }}>设置</h2>
      {error && <div className="error-banner">{error}</div>}

      <div className="card">
        <h2>监测频率（计划 §30）</h2>
        <div className="row" style={{ marginBottom: 8 }}>
          <div className="form-item">
            <label>最小间隔（秒，最低 6）</label>
            <input type="number" min={6} value={intervalMin} onChange={(e) => setIntervalMin(e.target.value)} />
          </div>
          <div className="form-item">
            <label>最大间隔（秒）</label>
            <input type="number" min={6} value={intervalMax} onChange={(e) => setIntervalMax(e.target.value)} />
          </div>
        </div>
        <p className="muted">
          系统按课程分组共享查询，服务器错误时指数退避（10s/20s/40s/60s），不会高频轰炸教务系统。
        </p>
      </div>

      <div className="card">
        <h2>浏览器</h2>
        <div className="row">
          <div className="form-item">
            <label>浏览器通道</label>
            <select value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="edge">系统 Microsoft Edge（推荐）</option>
              <option value="chromium">Playwright Chromium</option>
            </select>
          </div>
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          浏览器通道修改需要重启后端生效。登录态保存在 browser_profile/，不会写入数据库或日志。
        </p>
      </div>

      <div className="row">
        <button className="btn" onClick={save}>
          保存设置
        </button>
        {saved && <span className="status-ok">已保存</span>}
      </div>

      {settings && (
        <div className="card">
          <h2>当前运行状态</h2>
          <div className="muted">
            引擎运行中：{settings.current.running ? "是" : "否"} · 当前生效间隔：{" "}
            {settings.current.interval_min ?? "-"}~{settings.current.interval_max ?? "-"} 秒
          </div>
        </div>
      )}
    </div>
  );
}
