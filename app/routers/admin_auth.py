"""管理员认证：登录 / 登出 / 当前会话。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.deps import client_ip, require_admin
from app.ratelimit import rate_limiter
from app.security import (
    CSRF_COOKIE_NAME,
    create_session_token,
    hash_password,
    needs_rehash,
    new_csrf_token,
    verify_password,
)

router = APIRouter(prefix="/api/admin", tags=["admin-auth"])

# 登录失败限流：同一 IP 5 分钟内最多 10 次尝试
LOGIN_WINDOW = 300
LOGIN_LIMIT = 10


def _set_session_cookies(response: Response, token: str, csrf_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,                 # JS 读不到，防 XSS 窃取
        secure=settings.cookie_secure,  # HTTPS 下必须为 True
        samesite="lax",
        path="/",
    )
    # CSRF token 必须能被前端 JS 读到，所以不是 httponly
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=settings.session_max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=schemas.LoginResult)
def login(payload: schemas.LoginRequest, request: Request, response: Response,
          db: Session = Depends(get_db)):
    ip = client_ip(request)
    wait = rate_limiter.check(f"login:{ip}", LOGIN_WINDOW, LOGIN_LIMIT)
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"尝试过于频繁，请 {int(wait) + 1} 秒后再试",
        )

    admin = (
        db.query(models.AdminUser)
        .filter(models.AdminUser.username == payload.username.strip())
        .first()
    )
    if admin is None or not verify_password(payload.password, admin.password_hash):
        # 不区分"用户不存在"和"密码错误"，避免用户名枚举
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 登录成功顺手升级哈希参数
    if needs_rehash(admin.password_hash):
        admin.password_hash = hash_password(payload.password)
    admin.last_login_at = models.utcnow()
    db.commit()
    db.refresh(admin)

    token = create_session_token(admin.username)
    csrf_token = new_csrf_token()
    _set_session_cookies(response, token, csrf_token)

    return schemas.LoginResult(
        admin=schemas.AdminOut.model_validate(admin), csrf_token=csrf_token
    )


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.session_cookie, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=schemas.AdminOut)
def me(admin: models.AdminUser = Depends(require_admin)):
    return schemas.AdminOut.model_validate(admin)
