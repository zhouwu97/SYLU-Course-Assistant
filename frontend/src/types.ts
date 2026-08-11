// 与 backend/app 的 API 输出对应的类型（计划 §33、§38）

export type SectionStatus = "UNKNOWN" | "AVAILABLE" | "FULL";

export interface Meeting {
  weekday: number;
  start_period: number;
  end_period: number;
  weeks: number[];
  place: string;
}

export interface CourseSection {
  jxb_id: string;
  jxbmc: string;
  kch: string;
  kch_id: string;
  kcmc: string;
  teacher: string;
  meetings: Meeting[];
  place: string;
  selected: number | null;
  capacity: number | null;
  status: SectionStatus;
}

export interface Course {
  kch_id: string;
  kch: string;
  name: string;
  category: string;
  section_count: number;
  sections: CourseSection[];
}

export interface Preference {
  preferred: { sections: string[]; teachers: string[]; times: string[]; places: string[] };
  avoid: { teachers: string[]; times: string[]; places: string[] };
  fallback: {
    allow_other_teacher: boolean;
    allow_other_time: boolean;
    forbid_schedule_conflict: boolean;
    forbid_full: boolean;
    forbid_unknown_capacity: boolean;
    avoid_almost_full: boolean;
    order: string[];
    max_fallback_depth: number;
  };
}

export interface Intent {
  intent_id: string;
  course_id: string;
  course_name: string;
  category: string;
  keyword: string;
  priority: number;
  mode: "notify" | "confirm" | "auto";
  state: string;
  preference: Preference;
  existing_schedule: Meeting[];
  created_at: string;
  updated_at: string;
}

export interface Candidate {
  section: string;
  jxb_id: string;
  teacher: string;
  time: string;
  availability: SectionStatus;
  selected: number | null;
  capacity: number | null;
  tier: number;
  score: number;
  reasons: string[];
}

export interface Decision {
  intent_id: string;
  requested: Record<string, string | null>;
  candidates: Candidate[];
  decision: { action: string; section: string | null; jxb_id: string | null; message: string };
}

export interface TaskEvent {
  event_id: string;
  intent_id: string;
  ts: string;
  level: "info" | "warn" | "error" | "success";
  message: string;
}

export interface EngineStatus {
  loggedIn: boolean;
  engineRunning: boolean;
  enginePaused: boolean;
  activeTasks: number;
  lastCheckAt: string | null;
  nextCheckInSeconds: number | null;
  intervalSeconds: number | null;
}

export interface SettingsData {
  interval_min: number;
  interval_max: number;
  browser_channel: string;
  current: { interval_min: number | null; interval_max: number | null; running: boolean };
}

// 时间标签（后端 Meeting 结构 -> 中文）
const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

export function meetingLabel(m: Meeting): string {
  const w = WEEKDAYS[m.weekday - 1] ?? m.weekday;
  const weeks = m.weeks.length ? `(${m.weeks[0]}-${m.weeks[m.weeks.length - 1]}周)` : "";
  return `周${w}${m.start_period}-${m.end_period}节${weeks}`;
}

export function statusClass(status: SectionStatus | string): string {
  if (status === "AVAILABLE") return "status-ok";
  if (status === "FULL") return "status-full";
  return "status-unknown";
}

export function stateClass(state: string): string {
  if (["SUCCESS"].includes(state)) return "status-ok";
  if (["FULL", "CONFLICT", "REJECTED", "SESSION_EXPIRED", "UNKNOWN_ERROR", "NETWORK_ERROR"].includes(state))
    return "status-full";
  if (["WAITING", "CANDIDATE_FOUND", "WAITING_CONFIRMATION", "DISCOVERING"].includes(state)) return "status-wait";
  return "status-unknown";
}

export const STATE_LABELS: Record<string, string> = {
  IDLE: "空闲", DISCOVERING: "发现中", WAITING: "候补中", CANDIDATE_FOUND: "发现候选",
  WAITING_CONFIRMATION: "待确认", SUBMITTING: "提交中", SUCCESS: "已选",
  FULL: "已满", CONFLICT: "冲突", REJECTED: "被拒绝", SESSION_EXPIRED: "登录失效",
  NETWORK_ERROR: "网络错误", UNKNOWN_ERROR: "未知错误", PAUSED: "已暂停",
};

export const MODE_LABELS: Record<string, string> = {
  notify: "仅提醒", confirm: "确认后选", auto: "全自动",
};

export const CATEGORY_LABELS: Record<string, string> = {
  main: "主修课程", general: "通识选修课", sport: "体育分项",
};

export function fmtTime(ts: string | null | undefined): string {
  if (!ts) return "-";
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString("zh-CN", { hour12: false });
}
