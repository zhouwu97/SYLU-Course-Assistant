# SYLU Course Assistant v3

沈阳理工大学正方自主选课系统的本地选课决策 + 自动候补执行工具。

v2（单文件命令行脚本，`legacy/sylu_course_auto_v2.py`）已冻结。v3 从"指定教学班自动点击"
升级为"可视化课程发现 + 用户偏好决策 + 自动候补执行"系统。

## 架构

```text
┌─────────────────────────────────────────┐
│  本地 Web 前端（React + TS + Vite）       │
│  总览 / 找课程 / 选课计划 / 自动候补 / 设置 │
└──────────────────┬──────────────────────┘
                   │ REST + WebSocket (localhost:8765)
┌──────────────────▼──────────────────────┐
│ Python Backend（FastAPI + SQLite）        │
│  Course Discovery / Ranking / Conflict   │
│  Preference Engine / Watcher / 状态机     │
│  Playwright Adapter（zfsoft/）            │
└──────────────────┬──────────────────────┘
                   │ 页面正常校验链 checkCourse_* -> saveCourse
            正方教务系统（浏览器会话）
```

- 用户决定"想上什么课、能接受到什么程度"；程序负责寻找当前最优可选教学班。
- 提交操作通过 Playwright 点击学校页面真实"选课"按钮，沿用学校自身
  `checkCourse_* -> saveCourse` 校验链，不绕过验证码 / 身份认证 / 资格检查 / 容量检查 / 冲突检查。
- 正方教务相关 DOM、endpoint、字段、选择器全部锁在 `backend/app/adapters/zfsoft/`，
  Domain / Service 层不依赖具体页面字段。
- Cookie / JSESSIONID 只存在于 Playwright profile（`browser_profile/`）内部，
  不写入 SQLite、不写入日志、不下发给前端。
- 监测任务按课程查询分组共享请求；默认间隔 8~15 秒，禁止小于 6 秒；服务器错误指数退避
  （10s/20s/40s/60s）。
- 决策模型：Hard Constraints → Fallback Tier → Preference Score → Availability → 排序。
  每个候选带 `score/reasons/tier/availability`，前端解释为什么推荐（非黑箱）。

## 安装

```powershell
py -m pip install -r requirements.txt
py -m playwright install chromium
cd frontend; npm install; npm run build; cd ..
```

## 运行

```powershell
.\scripts\start.ps1
# 浏览器访问 http://localhost:8765
```

首次使用：在"总览"页点击"打开教务登录"，在弹出的浏览器中完成学校登录/验证码，
登录态保存在 `browser_profile/`，之后一般可直接自动运行。

## 核心功能

- 找课程：按名称/课程号/教师搜索，展示全部真实教学班（教师/时间/地点/人数/状态）
- 选课计划：首选教学班/教师/时间/地点、黑名单（教师/时间/地点）、替代顺序（可排序）、
  冲突排除、人数未知/只剩 1 名额排除、三种执行模式（仅提醒/确认后选/全自动）
- 决策预览：保存前明确显示"系统当前会选择哪个班"和原因
- 自动候补：多课程独立任务、课程优先级、WebSocket 实时事件推送、引擎暂停/恢复
- 模式 B：发现替代班弹窗"选这个班 / 继续等首选"
- section-level 失败（满/冲突）自动标记并继续找下一个班；登录失效才暂停整门课

## 项目结构

```text
sylu-course-assistant/
├─ legacy/                      # 冻结的 v2 脚本
├─ backend/
│  ├─ app/
│  │  ├─ api/                   # FastAPI 路由（auth/courses/plans/tasks/settings/ws）
│  │  ├─ domain/                # Course/Section/Meeting/Preference/Intent/Decision/状态机
│  │  ├─ services/              # 课程发现 / 排序 / 冲突 / 选课服务
│  │  ├─ adapters/zfsoft/       # 正方页面适配层（唯一知道 jxb_id 的地方）
│  │  ├─ workers/               # 候补监测引擎（Watcher）
│  │  └─ storage/               # SQLite 持久化
│  └─ tests/                    # domain / adapters / services / api 测试
├─ frontend/                    # React + TypeScript + Vite
├─ data/                        # sylu.db（用户计划与偏好，不含认证信息）
├─ browser_profile/             # Playwright 持久化浏览器（含登录态，勿提交）
├─ logs/debug.log               # 开发日志（Cookie/token 自动打码）
└─ scripts/start.ps1
```

## 测试

```powershell
py -m pytest -q
```

覆盖：时间/周次解析与冲突引擎、教学班解析（JSON/DOM/文本块）、提交结果分类、
课程发现分组、决策引擎（首选满员 fallback、黑名单永不入选、冲突淘汰、替代顺序、模式）、
API/WebSocket/确认流程。

## API 概览

```text
GET  /api/status               引擎/登录状态
POST /api/auth/open            打开浏览器等待登录
GET  /api/auth/status          登录状态（只返回布尔）
GET  /api/course-categories
GET  /api/courses?q=&category=
GET  /api/courses/{id}/sections?q=
GET  /api/schedule/current
POST/GET/PUT/DELETE /api/intents
POST /api/intents/{id}/preview 决策预览
POST /api/intents/{id}/start|pause|confirm|decline
GET  /api/tasks | /api/events
POST /api/engine/pause|resume
GET/PUT /api/settings
WS   /api/ws                   实时事件推送
```

Swagger 自测：http://localhost:8765/docs
