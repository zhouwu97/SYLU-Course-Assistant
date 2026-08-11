import argparse
import asyncio
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE = "https://jxw.sylu.edu.cn"
DEFAULT_URL = BASE + "/xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default"

SUCCESS_WORDS = ("选课成功", "选择成功", "操作成功", "成功", "已选")
RETRY_WORDS = ("人数已满", "课程已满", "已满", "无余量", "余量不足", "容量已满", "稍后重试", "繁忙")
STOP_WORDS = ("时间冲突", "冲突", "不满足", "限制", "不能选", "不可选", "失败", "超过", "已选过", "重复")
ACTION_LABELS = ("选课", "选择", "报名")
CAP_RE = re.compile(r"(?<!\d)(\d{1,4})\s*/\s*(\d{1,4})(?!\d)")


@dataclass
class Target:
    course: str
    class_name: str = ""
    teacher: str = ""
    time: str = ""
    place: str = ""
    priority: int = 100

    @classmethod
    def from_dict(cls, d: dict[str, Any]):
        return cls(
            course=str(d.get("course", "")).strip(),
            class_name=str(d.get("class_name", "")).strip(),
            teacher=str(d.get("teacher", "")).strip(),
            time=str(d.get("time", "")).strip(),
            place=str(d.get("place", "")).strip(),
            priority=int(d.get("priority", 100)),
        )

    def describe(self) -> str:
        parts = [f"课程={self.course}"]
        if self.class_name:
            parts.append(f"教学班={self.class_name}")
        if self.teacher:
            parts.append(f"教师={self.teacher}")
        if self.time:
            parts.append(f"时间={self.time}")
        if self.place:
            parts.append(f"地点={self.place}")
        return "，".join(parts)


def beep(ok: bool = False):
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.Beep(1600 if ok else 1100, 500)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


def load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"配置文件不存在: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def build_targets(args, cfg: dict[str, Any]) -> list[Target]:
    if args.course:
        return [Target(
            course=args.course,
            class_name=args.class_name or "",
            teacher=args.teacher or "",
            time=args.time or "",
            place=args.place or "",
            priority=1,
        )]
    targets = [Target.from_dict(x) for x in cfg.get("targets", [])]
    targets = [x for x in targets if x.course]
    if not targets:
        raise SystemExit("请通过 --course 指定目标，或在 config.json 中填写 targets。")
    return sorted(targets, key=lambda x: x.priority)


async def visible_text(page) -> str:
    try:
        body = await page.locator("body").inner_text(timeout=2500)
        return " ".join(body.split())
    except Exception:
        return ""


async def ensure_login(page, url: str, wait_seconds: int):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass

    end = asyncio.get_running_loop().time() + wait_seconds
    announced = False
    while asyncio.get_running_loop().time() < end:
        text = await visible_text(page)
        if "自主选课" in text and "/xsxk/" in page.url:
            return
        if not announced:
            print("\n[登录] 浏览器已打开。首次运行请正常完成学校登录/身份验证。")
            print("[登录] 登录后进入‘自主选课’页面；脚本会自动继续。以后会复用 browser_profile。")
            announced = True
        await page.wait_for_timeout(1000)
        # 登录完成后如果还停在首页，尝试回到目标页面
        if "用户登录" not in text and "/xsxk/" not in page.url:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            except Exception:
                pass
    raise SystemExit("等待登录超时。请重新运行，并在浏览器中完成登录。")


async def click_tab(page, tab: str) -> bool:
    if not tab:
        return True
    # 正方页面常见 tab 是 a/li；只点可见且文本精确/包含匹配的控件。
    candidates = page.locator("a,button,li")
    for i in range(await candidates.count()):
        loc = candidates.nth(i)
        try:
            if not await loc.is_visible():
                continue
            text = " ".join((await loc.inner_text()).split())
            if text == tab or (tab in text and len(text) <= len(tab) + 8):
                await loc.click(timeout=2500)
                await page.wait_for_timeout(700)
                print(f"[页面] 已切换到：{tab}")
                return True
        except Exception:
            continue
    print(f"[页面] 未找到 tab：{tab}（继续使用当前 tab）")
    return False


async def get_search_input(page):
    selectors = [
        "input[placeholder*='课程号']",
        "input[placeholder*='课程名称']",
        "input[placeholder*='教师']",
        "input[type='text']",
    ]
    for sel in selectors:
        locs = page.locator(sel)
        for i in range(await locs.count()):
            loc = locs.nth(i)
            try:
                if await loc.is_visible() and await loc.is_enabled():
                    box = await loc.bounding_box()
                    if box and box["width"] > 120:
                        return loc
            except Exception:
                pass
    return None


async def set_search_keyword(page, keyword: str) -> bool:
    inp = await get_search_input(page)
    if inp is None:
        return False
    try:
        current = await inp.input_value()
    except Exception:
        current = ""
    if current != keyword:
        await inp.fill(keyword)
    return True


async def click_query(page) -> bool:
    selectors = [
        "button:has-text('查询')",
        "a:has-text('查询')",
        "input[value='查询']",
    ]
    for sel in selectors:
        locs = page.locator(sel)
        for i in range(await locs.count()):
            loc = locs.nth(i)
            try:
                if await loc.is_visible() and await loc.is_enabled():
                    await loc.click(timeout=3000)
                    await page.wait_for_timeout(900)
                    return True
            except Exception:
                pass
    return False


async def action_candidates(page) -> list[dict[str, Any]]:
    """返回每个“选课”按钮及其祖先层文本。

    正方不同部署的 DOM 不统一，所以不假设一定是 <tr>。从按钮向上找最多 10 层，
    让课程标题、教学班、教师、时间、地点都能参与匹配。
    """
    locs = page.locator("button,a,input[type='button'],input[type='submit']")
    out: list[dict[str, Any]] = []
    for i in range(await locs.count()):
        loc = locs.nth(i)
        try:
            if not await loc.is_visible() or not await loc.is_enabled():
                continue
            label = (await loc.inner_text()).strip() if await loc.evaluate("e => e.tagName !== 'INPUT'") else (await loc.get_attribute("value") or "").strip()
            label = " ".join(label.split())
            if label not in ACTION_LABELS:
                continue
            info = await loc.evaluate("""
                el => {
                    const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
                    const layers = [];
                    let p = el;
                    for (let n = 0; p && n < 11; n++, p = p.parentElement) {
                        const t = norm(p.innerText || p.textContent || '');
                        if (t) layers.push({
                            tag: p.tagName,
                            id: p.id || '',
                            cls: String(p.className || ''),
                            text: t.slice(0, 2200)
                        });
                    }
                    return {layers};
                }
            """)
            out.append({"locator": loc, "label": label, "layers": info.get("layers", [])})
        except Exception:
            continue
    return out


def score_candidate(c: dict[str, Any], target: Target) -> tuple[int, str] | None:
    layers = c.get("layers", [])
    if not layers:
        return None

    required = [x for x in [target.class_name, target.teacher, target.time, target.place] if x]
    best_score = -1
    best_text = ""

    for depth, layer in enumerate(layers):
        text = layer.get("text", "")
        # 指定了行级约束时必须全部命中同一祖先容器，避免跨行误点。
        if required and not all(x in text for x in required):
            continue
        # 课程名可能在课程面板标题而不在单行；如果指定了教学班，可由教学班承担精确定位。
        course_hit = target.course in text
        if not course_hit and not target.class_name:
            continue

        score = 1000 - depth * 20
        if course_hit:
            score += 120
        if target.class_name and target.class_name in text:
            score += 300
        if target.teacher and target.teacher in text:
            score += 160
        if target.time and target.time in text:
            score += 100
        if target.place and target.place in text:
            score += 80
        # 越短的容器越接近单个教学班，避免拿整个页面作为匹配容器。
        score -= min(len(text) // 80, 120)
        if score > best_score:
            best_score = score
            best_text = text

    if best_score < 0:
        return None
    return best_score, best_text


def capacity_from_text(text: str) -> tuple[int | None, int | None, bool]:
    if "已满" in text:
        return None, None, True
    m = CAP_RE.search(text)
    if not m:
        return None, None, False
    selected, cap = int(m.group(1)), int(m.group(2))
    return selected, cap, cap > 0 and selected >= cap


async def find_best_action(page, target: Target):
    candidates = await action_candidates(page)
    scored = []
    for c in candidates:
        s = score_candidate(c, target)
        if s is not None:
            scored.append((s[0], c, s[1]))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0]


async def parse_json_response(resp) -> dict[str, Any]:
    try:
        data = await resp.json()
        if isinstance(data, dict):
            return data
        return {"data": data}
    except Exception:
        try:
            return {"text": (await resp.text())[:1000]}
        except Exception:
            return {}


def classify_result(data: dict[str, Any], page_text: str = "") -> tuple[str, str]:
    msg = str(data.get("msg") or data.get("message") or data.get("text") or "").strip()
    flag = str(data.get("flag", "")).strip()
    combined = (msg + " " + page_text[-2500:]).strip()

    if flag == "1" or any(w in combined for w in SUCCESS_WORDS):
        return "success", msg or "服务器返回成功"
    if any(w in combined for w in RETRY_WORDS):
        return "retry", msg or "课程可能已满/繁忙"
    if any(w in combined for w in STOP_WORDS):
        return "stop", msg or "出现冲突或限制"
    if flag and flag != "1":
        return "retry", msg or f"服务器 flag={flag}"
    return "unknown", msg or "未识别服务器反馈"


async def click_and_wait_result(page, locator, timeout_ms: int = 12000):
    # 用户抓包显示最终保存请求包含 xkBcZyZzxkYzb.html；前面的 cxXkTitleMsg 是校验链。
    try:
        async with page.expect_response(
            lambda r: "xkBcZyZzxkYzb.html" in r.url and r.request.method == "POST",
            timeout=timeout_ms,
        ) as info:
            await locator.click(timeout=4000)
        resp = await info.value
        data = await parse_json_response(resp)
        return data, resp.url
    except PlaywrightTimeoutError:
        # 某些校验失败会在 saveCourse 前终止；此时读取页面提示即可。
        await page.wait_for_timeout(900)
        return {}, ""


async def maybe_dismiss_dialogs(page):
    # 只处理常见确认/提示按钮，不去点“选课”之外的业务控件。
    for text in ("确定", "确认", "知道了", "关闭"):
        try:
            loc = page.locator(f"button:has-text('{text}'), a:has-text('{text}')")
            if await loc.count() and await loc.first.is_visible():
                await loc.first.click(timeout=1200)
                await page.wait_for_timeout(250)
                return
        except Exception:
            pass


async def run(args):
    cfg = load_config(args.config)
    targets = build_targets(args, cfg)

    tab = args.tab if args.tab is not None else str(cfg.get("tab", ""))
    interval_min = args.interval_min if args.interval_min is not None else float(cfg.get("interval_min", 8.0))
    interval_max = args.interval_max if args.interval_max is not None else float(cfg.get("interval_max", 14.0))
    dry_run = bool(args.dry_run or cfg.get("dry_run", False))
    profile = args.profile or str(cfg.get("profile", Path(__file__).with_name("browser_profile")))

    if interval_min < 6:
        raise SystemExit("interval_min 最低设为 6 秒，避免对教务系统造成过高请求压力。")
    if interval_max < interval_min:
        raise SystemExit("interval_max 不能小于 interval_min。")

    print("\n=== SYLU 自主选课自动化 v2 ===")
    print("模式:", "只监测/不点击" if dry_run else "自动选课")
    print("tab:", tab or "保持页面当前 tab")
    print("检查间隔:", f"{interval_min:.1f}~{interval_max:.1f}s")
    for i, t in enumerate(targets, 1):
        print(f"目标 {i} [优先级 {t.priority}]: {t.describe()}")
    print("说明: 使用学校页面自己的‘选课’按钮和校验链，不硬编码 Cookie/JSESSIONID。")

    if not args.yes:
        input("\n确认目标无误后按 Enter 启动（Ctrl+C 取消）……")

    async with async_playwright() as p:
        launch_kw = dict(
            user_data_dir=profile,
            headless=False,
            viewport={"width": 1450, "height": 950},
        )
        try:
            if args.browser == "edge":
                context = await p.chromium.launch_persistent_context(channel="msedge", **launch_kw)
            else:
                context = await p.chromium.launch_persistent_context(**launch_kw)
        except Exception as e:
            if args.browser == "edge":
                print(f"[浏览器] Edge 启动失败，回退 Playwright Chromium：{e}")
                context = await p.chromium.launch_persistent_context(**launch_kw)
            else:
                raise

        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(4500)
        await ensure_login(page, args.url, args.wait_login)
        await click_tab(page, tab)

        last_keyword = None
        cycle = 0
        while True:
            cycle += 1
            try:
                # 按优先级逐个目标扫描；同一课程名只需要查询一次。
                for target in targets:
                    if target.course != last_keyword:
                        ok = await set_search_keyword(page, target.course)
                        if not ok:
                            print(f"[{cycle}] 未定位到搜索框")
                        if not await click_query(page):
                            print(f"[{cycle}] 未定位到‘查询’按钮")
                        last_keyword = target.course
                    else:
                        # 同一关键词也需要刷新余量
                        await click_query(page)

                    best = await find_best_action(page, target)
                    if best is None:
                        print(f"[{cycle}] 未找到：{target.describe()}")
                        continue

                    score, item, text = best
                    selected, cap, full = capacity_from_text(text)
                    cap_text = "容量未知"
                    if selected is not None and cap is not None:
                        cap_text = f"{selected}/{cap}"
                    print(f"[{cycle}] 命中：{target.describe()} | {cap_text} | 匹配分={score}")

                    if full:
                        print("       当前显示已满，等待下一轮。")
                        continue

                    beep(False)
                    if dry_run:
                        print("       [dry-run] 已发现可点击‘选课’，不执行。")
                        continue

                    print("       [提交] 点击页面正常‘选课’按钮，等待服务器结果……")
                    data, endpoint = await click_and_wait_result(page, item["locator"])
                    page_text = await visible_text(page)
                    state, msg = classify_result(data, page_text)
                    if endpoint:
                        print(f"       [接口] {endpoint.split('?')[0]}")
                    print(f"       [结果] {state}: {msg}")

                    if state == "success":
                        beep(True)
                        print("\n[完成] 目标课程已返回成功/已选状态，程序停止。")
                        await context.close()
                        return
                    if state == "stop":
                        beep(False)
                        print("\n[停止] 检测到冲突/限制类反馈，避免重复提交。请查看浏览器提示。")
                        if args.keep_open:
                            await asyncio.to_thread(input, "按 Enter 关闭浏览器……")
                        await context.close()
                        return

                    # retry/unknown: 关闭可能的提示框，进入下一轮，不在当前轮连点。
                    await maybe_dismiss_dialogs(page)
                    break

            except KeyboardInterrupt:
                print("\n用户终止。")
                await context.close()
                return
            except PlaywrightTimeoutError:
                print(f"[{cycle}] 页面响应超时，本轮跳过。")
            except Exception as e:
                print(f"[{cycle}] 异常：{type(e).__name__}: {e}")

            delay = random.uniform(interval_min, interval_max)
            print(f"       下次检查约 {delay:.1f}s 后")
            await asyncio.sleep(delay)


def parse_args():
    ap = argparse.ArgumentParser(description="沈阳理工大学正方自主选课自动化（浏览器会话 + 正常页面校验链）")
    ap.add_argument("--config", help="JSON 配置文件；支持多目标优先级")
    ap.add_argument("--course", help="课程名关键字；给出后忽略 config.targets")
    ap.add_argument("--class-name", default="", help="教学班关键字，如 羽毛球5-11")
    ap.add_argument("--teacher", default="", help="教师关键字")
    ap.add_argument("--time", default="", help="上课时间关键字")
    ap.add_argument("--place", default="", help="地点关键字")
    ap.add_argument("--tab", default=None, help="如 体育分项 / 通识选修课 / 主修课程")
    ap.add_argument("--interval-min", type=float, default=None)
    ap.add_argument("--interval-max", type=float, default=None)
    ap.add_argument("--profile", default="", help="持久化浏览器目录")
    ap.add_argument("--browser", choices=["edge", "chromium"], default="edge")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--wait-login", type=int, default=300, help="首次登录等待秒数")
    ap.add_argument("--dry-run", action="store_true", help="只监测，不点击选课")
    ap.add_argument("--yes", action="store_true", help="启动时不再要求 Enter 确认")
    ap.add_argument("--keep-open", action="store_true", help="冲突/限制时保持浏览器等待人工查看")
    return ap.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
