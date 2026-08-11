// 找课程（计划 §4、§5）：搜索 -> 真实教学班表格（状态/教师/时间/地点/容量）
import { useState } from "react";
import { get } from "../api/client";
import { CATEGORY_LABELS, Course, meetingLabel, statusClass } from "../types";

export default function Courses() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const search = async () => {
    if (!q.trim()) return;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ q: q.trim() });
      if (category) {
        params.set("category", category);
        params.set("tab", CATEGORY_LABELS[category] ?? "");
      }
      const r = await get<{ courses: Course[] }>(`/api/courses?${params}`);
      setCourses(r.courses);
    } catch (e) {
      setError((e as Error).message);
      setCourses(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: 14 }}>找课程</h2>
      {error && <div className="error-banner">{error}</div>}

      <div className="searchbar">
        <input
          type="text"
          placeholder="搜索课程名称 / 课程号 / 教师，如 羽毛球"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <button className="btn" onClick={search} disabled={loading}>
          {loading ? "查询中..." : "查询"}
        </button>
      </div>

      <div className="tabs">
        <button className={`tab ${category === "" ? "active" : ""}`} onClick={() => setCategory("")}>
          全部
        </button>
        {Object.entries(CATEGORY_LABELS).map(([id, label]) => (
          <button
            key={id}
            className={`tab ${category === id ? "active" : ""}`}
            onClick={() => setCategory(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {courses &&
        courses.map((c) => (
          <div className="card" key={c.kch_id}>
            <div
              className="row between"
              style={{ cursor: "pointer" }}
              onClick={() => setExpanded(expanded === c.kch_id ? null : c.kch_id)}
            >
              <div>
                <strong>{c.name}</strong>
                <span className="muted" style={{ marginLeft: 10 }}>
                  {c.kch} · {c.section_count} 个教学班
                </span>
              </div>
              <span className="muted">{expanded === c.kch_id ? "收起 ▲" : "展开 ▼"}</span>
            </div>

            {expanded === c.kch_id && (
              <table style={{ marginTop: 10 }}>
                <thead>
                  <tr>
                    <th>状态</th>
                    <th>教学班</th>
                    <th>教师</th>
                    <th>时间</th>
                    <th>地点</th>
                    <th>已选/容量</th>
                  </tr>
                </thead>
                <tbody>
                  {c.sections.map((s) => (
                    <tr key={s.jxb_id}>
                      <td className={statusClass(s.status)}>
                        <span className="status-dot" />
                        {s.status === "AVAILABLE" ? "可选" : s.status === "FULL" ? "已满" : "未知"}
                      </td>
                      <td>{s.jxbmc}</td>
                      <td>{s.teacher || "-"}</td>
                      <td>{s.meetings.map(meetingLabel).join("、") || "-"}</td>
                      <td>{s.place || "-"}</td>
                      <td>{s.selected != null && s.capacity != null ? `${s.selected}/${s.capacity}` : "未知"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}

      {courses && courses.length === 0 && !loading && (
        <div className="card muted">没有找到匹配的课程，试试其他关键词。</div>
      )}
    </div>
  );
}
