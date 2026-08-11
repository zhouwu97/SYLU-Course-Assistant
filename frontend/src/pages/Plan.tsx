// 选课计划（计划 §6、§7、§8、§24）：添加意图 + 偏好规则 + 决策预览
import { useState } from "react";
import { post } from "../api/client";
import { Decision, Intent, Preference, stateClass } from "../types";

const EMPTY_PREF: Preference = {
  preferred: { sections: [], teachers: [], times: [], places: [] },
  avoid: { teachers: [], times: [], places: [] },
  fallback: {
    allow_other_teacher: true,
    allow_other_time: true,
    forbid_schedule_conflict: true,
    forbid_full: true,
    forbid_unknown_capacity: false,
    avoid_almost_full: false,
    order: ["same_teacher_other_time", "other_teacher_same_time", "other_teacher_other_time"],
    max_fallback_depth: 3,
  },
};

const ORDER_LABELS: Record<string, string> = {
  same_teacher_other_time: "1. 同教师 + 其他时间",
  other_teacher_same_time: "2. 其他教师 + 原时间",
  other_teacher_other_time: "3. 其他教师 + 其他时间",
};

function splitList(s: string): string[] {
  return s
    .split(/[,，、;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

export default function Plan() {
  const [keyword, setKeyword] = useState("");
  const [courseName, setCourseName] = useState("");
  const [category, setCategory] = useState("sport");
  const [priority, setPriority] = useState(1);
  const [mode, setMode] = useState<"notify" | "confirm" | "auto">("confirm");

  const [prefSections, setPrefSections] = useState("");
  const [prefTeachers, setPrefTeachers] = useState("");
  const [prefTimes, setPrefTimes] = useState("");
  const [prefPlaces, setPrefPlaces] = useState("");
  const [avoidTeachers, setAvoidTeachers] = useState("");
  const [avoidTimes, setAvoidTimes] = useState("");
  const [avoidPlaces, setAvoidPlaces] = useState("");
  const [allowOtherTeacher, setAllowOtherTeacher] = useState(true);
  const [allowOtherTime, setAllowOtherTime] = useState(true);
  const [forbidConflict, setForbidConflict] = useState(true);
  const [forbidUnknown, setForbidUnknown] = useState(false);
  const [avoidAlmostFull, setAvoidAlmostFull] = useState(false);
  const [order, setOrder] = useState<string[]>([...EMPTY_PREF.fallback.order]);

  const [intent, setIntent] = useState<Intent | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const buildPreference = (): Preference => ({
    preferred: {
      sections: splitList(prefSections),
      teachers: splitList(prefTeachers),
      times: splitList(prefTimes),
      places: splitList(prefPlaces),
    },
    avoid: {
      teachers: splitList(avoidTeachers),
      times: splitList(avoidTimes),
      places: splitList(avoidPlaces),
    },
    fallback: {
      allow_other_teacher: allowOtherTeacher,
      allow_other_time: allowOtherTime,
      forbid_schedule_conflict: forbidConflict,
      forbid_full: true,
      forbid_unknown_capacity: forbidUnknown,
      avoid_almost_full: avoidAlmostFull,
      order,
      max_fallback_depth: 3,
    },
  });

  const createIntent = async () => {
    setError("");
    setDecision(null);
    if (!keyword.trim()) {
      setError("请填写课程搜索关键词（如 羽毛球）");
      return;
    }
    setBusy("create");
    try {
      const body = {
        course_name: courseName || keyword.trim(),
        category,
        keyword: keyword.trim(),
        priority,
        mode,
        preference: buildPreference(),
      };
      const created = await post<Intent>("/api/intents", body);
      setIntent(created);
      await preview(created);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  const preview = async (target?: Intent) => {
    const t = target ?? intent;
    if (!t) return;
    setBusy("preview");
    setError("");
    try {
      setDecision(await post<Decision>(`/api/intents/${t.intent_id}/preview`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  const start = async () => {
    if (!intent) return;
    setBusy("start");
    try {
      setIntent(await post<Intent>(`/api/intents/${intent.intent_id}/start`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  const moveOrder = (idx: number, dir: -1 | 1) => {
    const next = [...order];
    const j = idx + dir;
    if (j < 0 || j >= next.length) return;
    [next[idx], next[j]] = [next[j], next[idx]];
    setOrder(next);
  };

  return (
    <div>
      <h2 style={{ marginBottom: 14 }}>添加选课计划</h2>
      {error && <div className="error-banner">{error}</div>}

      <div className="card">
        <h2>第一步：这门课是什么？</h2>
        <div className="form-grid">
          <div className="form-item">
            <label>搜索关键词（如 羽毛球）*</label>
            <input type="text" value={keyword} onChange={(e) => setKeyword(e.target.value)} />
          </div>
          <div className="form-item">
            <label>课程名称（如 体育5）</label>
            <input type="text" value={courseName} onChange={(e) => setCourseName(e.target.value)} />
          </div>
          <div className="form-item">
            <label>课程类别</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="main">主修课程</option>
              <option value="general">通识选修课</option>
              <option value="sport">体育分项</option>
            </select>
          </div>
          <div className="form-item">
            <label>课程优先级（1 最高，越小越优先）</label>
            <input type="number" min={1} value={priority} onChange={(e) => setPriority(Number(e.target.value))} />
          </div>
          <div className="form-item full">
            <label>执行模式</label>
            <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
              <option value="notify">仅提醒（发现可选班只通知，不提交）</option>
              <option value="confirm">确认后选（发现替代班弹窗等你确认）</option>
              <option value="auto">全自动（符合规则就直接选）</option>
            </select>
          </div>
        </div>
      </div>

      <div className="card">
        <h2>第二步：首选与排除（计划 §7、§8）</h2>
        <div className="form-grid">
          <div className="form-item">
            <label>首选教学班（逗号分隔，如 羽毛球5-11）</label>
            <input type="text" value={prefSections} onChange={(e) => setPrefSections(e.target.value)} placeholder="羽毛球5-11" />
          </div>
          <div className="form-item">
            <label>首选教师（逗号分隔）</label>
            <input type="text" value={prefTeachers} onChange={(e) => setPrefTeachers(e.target.value)} placeholder="孔令宇" />
          </div>
          <div className="form-item">
            <label>首选时间（如 周五5-6）</label>
            <input type="text" value={prefTimes} onChange={(e) => setPrefTimes(e.target.value)} placeholder="周五5-6" />
          </div>
          <div className="form-item">
            <label>首选地点</label>
            <input type="text" value={prefPlaces} onChange={(e) => setPrefPlaces(e.target.value)} />
          </div>
          <div className="form-item">
            <label>绝对不要这些教师（黑名单）</label>
            <input type="text" value={avoidTeachers} onChange={(e) => setAvoidTeachers(e.target.value)} placeholder="王XX" />
          </div>
          <div className="form-item">
            <label>绝对不要这些时间（如 周一1-2）</label>
            <input type="text" value={avoidTimes} onChange={(e) => setAvoidTimes(e.target.value)} placeholder="周一1-2" />
          </div>
          <div className="form-item full">
            <label>绝对不要这些地点</label>
            <input type="text" value={avoidPlaces} onChange={(e) => setAvoidPlaces(e.target.value)} />
          </div>
        </div>

        <h3>替代规则</h3>
        <div className="checkbox-row">
          <label>
            <input type="checkbox" checked={allowOtherTeacher} onChange={(e) => setAllowOtherTeacher(e.target.checked)} />
            允许更换教师
          </label>
          <label>
            <input type="checkbox" checked={allowOtherTime} onChange={(e) => setAllowOtherTime(e.target.checked)} />
            允许更换时间
          </label>
          <label>
            <input type="checkbox" checked={forbidConflict} onChange={(e) => setForbidConflict(e.target.checked)} />
            排除课表冲突
          </label>
          <label>
            <input type="checkbox" checked={forbidUnknown} onChange={(e) => setForbidUnknown(e.target.checked)} />
            不选人数未知的班
          </label>
          <label>
            <input type="checkbox" checked={avoidAlmostFull} onChange={(e) => setAvoidAlmostFull(e.target.checked)} />
            不选只剩 1 个名额的班
          </label>
        </div>

        <h3>替代优先级</h3>
        {order.map((o, idx) => (
          <div className="row" key={o} style={{ marginBottom: 6 }}>
            <span className="tag blue">{ORDER_LABELS[o]}</span>
            <button className="btn small secondary" onClick={() => moveOrder(idx, -1)} disabled={idx === 0}>
              ↑
            </button>
            <button className="btn small secondary" onClick={() => moveOrder(idx, 1)} disabled={idx === order.length - 1}>
              ↓
            </button>
          </div>
        ))}

        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn" onClick={createIntent} disabled={busy === "create"}>
            {busy === "create" ? "创建中..." : "创建意图并预览"}
          </button>
        </div>
      </div>

      {intent && (
        <div className="card">
          <div className="row between">
            <h2>
              决策预览：{intent.keyword}
              <span className={`badge ${stateClass(intent.state)}`} style={{ marginLeft: 10 }}>
                {intent.state}
              </span>
            </h2>
            <div className="row">
              <button className="btn secondary" onClick={() => preview()} disabled={busy === "preview"}>
                刷新预览
              </button>
              <button className="btn" onClick={start} disabled={busy === "start"}>
                启动自动候补
              </button>
            </div>
          </div>
          <p className="muted" style={{ marginBottom: 10 }}>
            系统当前会选择：{decision?.decision.section ?? "-"}（{decision?.decision.message ?? ""}）
          </p>

          {decision?.candidates.map((c) => (
            <div key={c.jxb_id} className={`candidate ${c.jxb_id === decision.decision.jxb_id ? "selected" : ""}`}>
              <div className="row between">
                <div>
                  <span className={stateClass(c.availability)}>
                    <span className="status-dot" />
                    {c.availability === "AVAILABLE" ? "可选" : c.availability === "FULL" ? "已满" : "未知"}
                  </span>
                  <strong style={{ marginLeft: 8 }}>{c.section}</strong>
                  <span className="muted" style={{ marginLeft: 10 }}>
                    {c.teacher} · {c.time}
                  </span>
                  {c.selected != null && c.capacity != null && (
                    <span className="muted" style={{ marginLeft: 10 }}>
                      {c.selected}/{c.capacity}
                    </span>
                  )}
                </div>
                <div>
                  <span className="score-big">{c.score}</span>
                  <span className="stars">{"★".repeat(Math.max(1, 6 - c.tier))}</span>
                  <span className="muted" style={{ marginLeft: 6 }}>层级 {c.tier}</span>
                </div>
              </div>
              <div className="reasons">
                {c.reasons.map((r) => (
                  <span className="tag" key={r}>
                    {r}
                  </span>
                ))}
              </div>
            </div>
          ))}
          {decision && decision.candidates.length === 0 && (
            <div className="muted">当前没有满足规则的教学班。</div>
          )}
        </div>
      )}
    </div>
  );
}
