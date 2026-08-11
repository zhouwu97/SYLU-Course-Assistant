"""正方教务系统端点定义（计划 §17：endpoints 锁在适配层）。

业务层禁止直接引用这些 URL；只有 adapters/zfsoft/ 知道它们。
"""
from __future__ import annotations

BASE = "https://jxw.sylu.edu.cn"

# 自主选课首页
INDEX_URL = BASE + "/xsxk/zzxkyzb_cxZzxkYzbIndex.html?gnmkdm=N253512&layout=default"

# 教学班列表查询接口的 URL 标记（XHR，查询后由页面 JS 发起）
LIST_URL_MARKER = "cxZzxkYzb"

# saveCourse 提交接口的 URL 标记（点击"选课"后页面 JS 发起，前面还有 checkCourse_* 校验链）
SAVE_URL_MARKER = "xkBcZyZzxkYzb"

# 已登录的标志：页面 URL 在选课模块下
LOGGED_IN_PATH_MARKER = "/xsxk/"

# 学生身份信息接口（用于补充教师信息，可选）
STUDENT_INFO_URL = BASE + "/xsxk/zzxkyzb_cxZzxkYzbIndex.html"
