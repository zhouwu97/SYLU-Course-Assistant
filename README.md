# SYLU Course Assistant v3

沈阳理工大学正方自主选课系统的本地选课决策 + 自动候补执行工具。

v2（单文件命令行脚本，`legacy/sylu_course_auto_v2.py`）已冻结。v3 从"指定教学班自动点击"
升级为"可视化课程发现 + 用户偏好决策 + 自动候补执行"系统。

## 设计原则

- 用户决定"想上什么课、能接受到什么程度"；程序负责寻找当前最优可选教学班。
- 提交操作通过 Playwright 点击学校页面真实"选课"按钮，沿用学校自身
  `checkCourse_* -> saveCourse` 校验链，不绕过验证码 / 身份认证 / 资格检查 / 容量检查 / 冲突检查。
- 正方教务相关 DOM、endpoint、字段、选择器全部锁在 `backend/app/adapters/zfsoft/`，
  Domain / Service 层不依赖具体页面字段。
- Cookie / JSESSIONID 只存在于 Playwright profile（`browser_profile/`）内部，
  不写入 SQLite、不写入日志、不下发给前端。
- 监测任务按课程查询分组共享请求；默认间隔 8~15 秒，禁止小于 5 秒；服务器错误指数退避。

## 项目结构

```text
sylu-course-assistant/
├─ legacy/                      # 冻结的 v2 脚本
├─ backend/
│  ├─ app/
│  │  ├─ api/                   # FastAPI 路由（auth/courses/plans/tasks/ws）
│  │  ├─ domain/                # Course / Section / Meeting / Preference / Task 模型
│  │  ├─ services/              # 课程发现 / 排序 / 冲突 / 偏好引擎 / 选课服务
│  │  ├─ adapters/zfsoft/       # 正方页面适配层（唯一知道 jxb_id 的地方）
│  │  ├─ workers/               # 候补监测 worker
│  │  └─ storage/               # SQLite 持久化
│  └─ tests/
├─ data/                        # sylu.db
├─ browser_profile/             # Playwright 持久化浏览器（含登录态，勿提交）
├─ logs/
└─ scripts/start.ps1
```

## 安装

```powershell
py -m pip install -r requirements.txt
py -m playwright install chromium
```

## 运行

```powershell
.\scripts\start.ps1
# 浏览器访问 http://localhost:8765
```

## 开发阶段

- Phase 0: 冻结 v2、项目骨架
- Phase 1: Domain 模型 + 课表冲突引擎
- Phase 2: zfsoft 适配器
- Phase 3: 真实课程 / 教学班发现
- Phase 4: 决策引擎（Hard Constraint + Fallback Tier + Ranking）
- Phase 5: FastAPI + SQLite
- Phase 6+: WebSocket 实时状态、React 前端、自动执行模式、完整异常处理

每完成一个 Phase 运行 `py -m pytest backend/tests` 并独立 commit。
