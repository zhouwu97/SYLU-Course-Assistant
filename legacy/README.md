# SYLU 自主选课自动化 v2

这一版针对你抓到的沈阳理工大学正方自主选课流程做了修复：

- 自动打开/复用浏览器登录会话；
- 自动切换 `主修课程 / 通识选修课 / 体育分项` tab（可选）；
- 自动填写课程关键字、点击查询并周期刷新；
- 不再假设课程一定在 `<tr>` 中，而是从每个“选课”按钮向上扫描祖先容器，匹配教学班/教师/时间/地点；
- 点击页面真实“选课”按钮，沿用学校页面自己的 `checkCourse_* -> saveCourse` 校验链；
- 监听最终 `xkBcZyZzxkYzb.html` POST 响应判断成功/已满/冲突；
- 多目标按 priority 顺序抢，命中一个成功后停止；
- 不把 Cookie/JSESSIONID 写入代码。

> 首次运行仍需要你在弹出的浏览器中完成学校登录/身份验证；登录态保存在本目录 `browser_profile`，后续通常可直接自动运行。

## 1. 安装

Windows PowerShell：

```powershell
cd sylu_course_helper_v2
py -m pip install -r requirements.txt
py -m playwright install chromium
```

默认优先调用系统 Microsoft Edge；如果 Edge 启动失败会回退 Playwright Chromium。

## 2. 单课程直接运行

例如只认指定教学班：

```powershell
py sylu_course_auto.py --course "体育5" --class-name "羽毛球5-11" --tab "体育分项" --yes --keep-open
```

再加老师限制：

```powershell
py sylu_course_auto.py --course "体育5" --class-name "羽毛球5-11" --teacher "孔令宇" --tab "体育分项" --yes --keep-open
```

只监测、不真的点选课：

```powershell
py sylu_course_auto.py --course "体育5" --class-name "羽毛球5-11" --tab "体育分项" --dry-run
```

## 3. 多目标优先级

复制：

```powershell
copy config.example.json config.json
```

修改 `config.json`：

```json
{
  "tab": "体育分项",
  "interval_min": 8,
  "interval_max": 14,
  "dry_run": false,
  "targets": [
    {
      "course": "体育5",
      "class_name": "羽毛球5-11",
      "teacher": "",
      "priority": 1
    },
    {
      "course": "体育5",
      "class_name": "羽毛球5-8",
      "teacher": "",
      "priority": 2
    }
  ]
}
```

然后：

```powershell
py sylu_course_auto.py --config config.json --yes --keep-open
```

或者双击 `run_example.bat`。

## 4. 为什么这一版不直接硬编码你抓到的 jxb_ids

你抓到的最终提交 `jxb_ids` 是一大段动态值；它不是列表接口里那个短的 `jxb_id`。页面在点击“选课”后会先走课程校验/明细链，再由页面自己的 JS 调用 `saveCourse`。因此 v2 直接自动点击目标教学班的真实“选课”按钮，让网页自己生成当前有效提交参数，并监听最终保存响应。

这样比把某次抓包里的 `jxb_ids / xkkz_id` 固定写死更稳，也不会因为这些值刷新后变化而选错。

## 5. 频率

默认 8~14 秒随机检查一次。脚本限制 `interval_min >= 6` 秒，不做多线程并发抢课，也不会绕过学校的资格、时间冲突、容量等正常校验。

## 6. 你之前发出的 Session

你截图/文本里出现过 `JSESSIONID`。本程序没有写入那个 Session，也不会读取它。建议你退出教务系统后重新登录一次，使旧 Session 失效。
