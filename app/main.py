"""应用入口：只做组装，业务逻辑在各 router / service 里。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import models
from app.config import settings
from app.database import SessionLocal, engine
from app.migrations.runner import upgrade_all
from app.routers import (
    admin_auth,
    admin_comments,
    admin_media,
    admin_pages,
    admin_posts,
    feeds,
    pages,
    public_comments,
    public_posts,
)
from app.security import hash_password

logger = logging.getLogger("blog")


def run_migrations() -> list[str]:
    executed = upgrade_all(engine)
    for name in executed:
        logger.info("迁移已执行: %s", name)
    return executed


def bootstrap_admin() -> None:
    """首次部署：如果库里没有管理员，用环境变量创建一个。"""
    with SessionLocal() as db:
        exists = db.execute(select(models.AdminUser.id).limit(1)).first()
        if exists:
            return
        import os

        username = os.getenv("ADMIN_USERNAME", "").strip()
        password = os.getenv("ADMIN_PASSWORD", "")
        if not username or not password:
            logger.warning("尚无管理员账号，请设置 ADMIN_USERNAME / ADMIN_PASSWORD")
            return
        db.add(models.AdminUser(username=username, password_hash=hash_password(password)))
        db.commit()
        logger.info("已创建管理员账号: %s", username)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    run_migrations()
    bootstrap_admin()
    if settings.secret_key_is_temporary:
        logger.warning("SECRET_KEY 未配置，正在使用临时密钥，重启后登录态失效")
    yield


app = FastAPI(
    title=f"{settings.site_name} API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.debug else None,
)

# 统一响应头：安全头 + 静态资源缓存。
# 服务器直接用隧道回源到 uvicorn，没有 nginx 兜底，安全头必须在这里加。
@app.middleware("http")
async def add_response_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=604800")
    elif path.startswith("/media/"):
        # 上传文件名带随机串，内容不变，可以长期缓存
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if path.startswith("/admin") or path.startswith("/api/admin"):
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    return response


# 静态资源；媒体文件生产环境由 nginx 直接托管，这里挂载保证本地开发可用
app.mount("/static", StaticFiles(directory=settings.static_dir, check_dir=False), name="static")
app.mount("/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media")

# ---- JSON 接口 ----
app.include_router(public_posts.router)
app.include_router(public_comments.router)
app.include_router(admin_auth.router)
app.include_router(admin_posts.router)
app.include_router(admin_comments.router)
app.include_router(admin_media.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "site": settings.site_name}


# ---- HTML 页面 ----
# 顺序很重要：/admin 和 /rss.xml 必须在 /{slug} 之前注册
app.include_router(feeds.router)
app.include_router(admin_pages.router)
app.include_router(pages.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """API 返回 JSON，页面返回统一错误页。"""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    if exc.status_code == 404:
        return pages.not_found(request)
    if exc.status_code >= 500:
        return pages.server_error(request)
    return Response(
        status_code=exc.status_code, content=str(exc.detail), media_type="text/plain; charset=utf-8"
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("未处理的异常: %s", exc)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "服务器内部错误"}, status_code=500)
    return pages.server_error(request)
