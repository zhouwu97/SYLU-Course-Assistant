"""正方教务系统页面选择器（计划 §17：selectors 锁在适配层）。

v2 经验：正方不同部署 DOM 不统一，不假设行一定是 <tr>，从"选课"按钮向上
扫描祖先容器。这里只负责"页面怎么点"，不负责业务判断。
"""
from __future__ import annotations

# 选课动作按钮文本
ACTION_LABELS = ("选课", "选择", "报名")
# 已选课程的标志按钮文本
WITHDRAW_LABELS = ("退选", "删除")

# tab 切换：正方常见 tab 是 a/li/button，文本精确或近似匹配
TAB_SELECTOR = "a,button,li"

# 搜索框
SEARCH_INPUT_SELECTORS = (
    "input[placeholder*='课程号']",
    "input[placeholder*='课程名称']",
    "input[placeholder*='教师']",
    "input[type='text']",
)

# 查询按钮
QUERY_BUTTON_SELECTORS = (
    "button:has-text('查询')",
    "a:has-text('查询')",
    "input[value='查询']",
)

# 所有可能承载"选课"动作的控件
ACTION_CONTROL_SELECTOR = "button,a,input[type='button'],input[type='submit']"

# 通用提示框按钮
DIALOG_BUTTONS = ("确定", "确认", "知道了", "关闭")

# 扫描"选课"按钮祖先层的最大深度（v2 用 11 层）
MAX_ANCESTOR_DEPTH = 11
