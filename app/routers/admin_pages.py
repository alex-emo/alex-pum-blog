"""后台 HTML 页面：只负责会话校验和外壳渲染，数据由浏览器调 /api/admin/* 接口。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.deps import get_current_admin_optional
from app.templating import render

router = APIRouter(prefix="/admin", tags=["admin-pages"], include_in_schema=False)


def _login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target += f"?{request.url.query}"
    return RedirectResponse(f"/admin/login?next={quote(target, safe='')}", status_code=303)


def _shell(request: Request, name: str, admin: models.AdminUser, **context) -> HTMLResponse:
    return render(
        request,
        name,
        admin=admin,
        nav=context.pop("nav", ""),
        **context,
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next: str = "/admin",
    admin: models.AdminUser | None = Depends(get_current_admin_optional),
):
    if admin is not None:
        return RedirectResponse("/admin", status_code=303)
    # 只允许站内跳转，避免开放重定向
    target = next if next.startswith("/") and not next.startswith("//") else "/admin"
    return render(request, "admin/login.html", next_url=target)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    admin: models.AdminUser | None = Depends(get_current_admin_optional),
):
    if admin is None:
        return _login_redirect(request)
    return _shell(request, "admin/dashboard.html", admin, nav="dashboard")


@router.get("/posts", response_class=HTMLResponse)
def posts_page(
    request: Request,
    admin: models.AdminUser | None = Depends(get_current_admin_optional),
):
    if admin is None:
        return _login_redirect(request)
    return _shell(request, "admin/posts.html", admin, nav="posts")


@router.get("/posts/new", response_class=HTMLResponse)
def new_post_page(
    request: Request,
    admin: models.AdminUser | None = Depends(get_current_admin_optional),
):
    if admin is None:
        return _login_redirect(request)
    return _shell(request, "admin/editor.html", admin, nav="posts", post_id=None)


@router.get("/posts/{post_id}/edit", response_class=HTMLResponse)
def edit_post_page(
    request: Request,
    post_id: int,
    admin: models.AdminUser | None = Depends(get_current_admin_optional),
    db: Session = Depends(get_db),
):
    if admin is None:
        return _login_redirect(request)
    return _shell(request, "admin/editor.html", admin, nav="posts", post_id=post_id)


@router.get("/comments", response_class=HTMLResponse)
def comments_page(
    request: Request,
    admin: models.AdminUser | None = Depends(get_current_admin_optional),
):
    if admin is None:
        return _login_redirect(request)
    return _shell(request, "admin/comments.html", admin, nav="comments")
