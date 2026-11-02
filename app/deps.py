"""FastAPI 依赖注入：数据库会话、当前管理员、CSRF 校验、客户端 IP。"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, read_session_token


def client_ip(request: Request) -> str:
    """取真实客户端 IP。

    部署在 nginx 后面，nginx 会把 X-Forwarded-For 传过来；
    只信任最后一跳（nginx 追加的那个），避免客户端伪造整条链。
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1][:64]
    return (request.client.host if request.client else "unknown")[:64]


def get_current_admin_optional(
    request: Request, db: Session = Depends(get_db)
) -> models.AdminUser | None:
    token = request.cookies.get(settings.session_cookie)
    if not token:
        return None
    username = read_session_token(token)
    if not username:
        return None
    return db.query(models.AdminUser).filter(models.AdminUser.username == username).first()


def require_admin(
    admin: models.AdminUser | None = Depends(get_current_admin_optional),
) -> models.AdminUser:
    """未登录统一返回 401，前端跳登录页。"""
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return admin


def require_admin_csrf(
    request: Request,
    admin: models.AdminUser = Depends(require_admin),
) -> models.AdminUser:
    """写操作依赖：已登录 + CSRF 双提交校验通过。"""
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    header_token = request.headers.get(CSRF_HEADER_NAME, "")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(status_code=403, detail="CSRF 校验失败，请刷新页面后重试")
    return admin
