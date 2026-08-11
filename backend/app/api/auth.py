"""认证 API（计划 §31、§32）。

只返回 loggedIn 布尔，绝不把 Cookie/JSESSIONID 暴露给前端。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
async def auth_status(request: Request) -> dict:
    state = request.app.state.app_state
    return {"loggedIn": await state.login_status()}


@router.post("/open")
async def auth_open(request: Request) -> dict:
    """打开浏览器并等待用户完成学校登录（首次需要验证码/统一认证）。"""
    state = request.app.state.app_state
    logged_in = await state.open_login(wait_timeout_s=300)
    if not logged_in:
        raise HTTPException(status_code=401, detail="等待登录超时")
    return {"loggedIn": True}
