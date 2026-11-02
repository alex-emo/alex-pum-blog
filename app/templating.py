"""Jinja2 模板环境：模板目录、过滤器、全局函数、通用上下文。

模板里只做展示逻辑，数据由路由组装好传进来；
URL 拼接、时间格式化这类规则集中在这里，避免散落在模板中。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app import models
from app.utils.text import reading_minutes
from app.utils.timez import format_dt, format_dt_full, isoformat_local


@dataclass
class Pagination:
    """分页信息 + 链接构造函数，模板里用 pagination.link(2)。"""

    page: int
    total_pages: int
    builder: Callable[[int], str]

    def link(self, number: int) -> str:
        return self.builder(number)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def prev_page(self) -> int:
        return max(1, self.page - 1)

    @property
    def next_page(self) -> int:
        return min(self.total_pages, self.page + 1)

    @property
    def numbers(self) -> list[int | None]:
        """窗口式页码，None 表示省略号。"""
        total, current = self.total_pages, self.page
        if total <= 7:
            return list(range(1, total + 1))
        pages: list[int | None] = [1]
        start, end = max(2, current - 1), min(total - 1, current + 1)
        if start > 2:
            pages.append(None)
        pages.extend(range(start, end + 1))
        if end < total - 1:
            pages.append(None)
        pages.append(total)
        return pages


def site_stats() -> dict[str, int]:
    """侧栏用：已发布文章数、有文章的标签数。每页两次 COUNT，SQLite 下开销可忽略。"""
    try:
        with SessionLocal() as db:
            posts = db.scalar(
                select(func.count(models.Post.id)).where(
                    models.Post.status == models.PostStatus.PUBLISHED
                )
            ) or 0
            tags = db.scalar(
                select(func.count(func.distinct(models.Tag.id)))
                .select_from(models.Tag)
                .join(models.post_tags, models.post_tags.c.tag_id == models.Tag.id)
                .join(models.Post, models.Post.id == models.post_tags.c.post_id)
                .where(models.Post.status == models.PostStatus.PUBLISHED)
            ) or 0
    except Exception:  # 迁移尚未跑完时不要让页面 500
        return {"posts": 0, "tags": 0}
    return {"posts": posts, "tags": tags}


def page_url(request: Request, base_path: str, number: int) -> str:
    """按 base_path + 页码 + 保留查询参数拼分页链接。"""
    params = dict(request.query_params)
    params.pop("page", None)
    path = base_path if number <= 1 else f"{base_path.rstrip('/')}/page/{number}"
    if not path:
        path = "/"
    return f"{path}?{urlencode(params)}" if params else path


def asset_url(url: str) -> str:
    """静态资源追加 mtime 版本号，避免浏览器缓存旧 JS/CSS。"""
    if not url.startswith("/static/"):
        return url
    path = settings.static_dir / url[len("/static/"):]
    try:
        version = int(path.stat().st_mtime)
    except OSError:
        return url
    return f"{url}?v={version}"


def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(settings.templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["dt"] = format_dt
    env.filters["dt_full"] = format_dt_full
    env.filters["iso"] = isoformat_local
    env.filters["reading_minutes"] = reading_minutes
    env.filters["post_url"] = lambda slug: f"/{slug}"
    env.filters["tag_url"] = lambda slug: f"/tag/{slug}"
    env.globals["settings"] = settings
    env.globals["asset_url"] = asset_url
    return env


templates = _build_env()


def render(
    request: Request,
    name: str,
    *,
    status_code: int = 200,
    **context,
) -> HTMLResponse:
    """渲染模板；统一注入站点配置、当前路径和查询参数。"""
    ctx = {
        "request": request,
        "settings": settings,
        "url_path": request.url.path,
        "query": dict(request.query_params),
        "stats": site_stats(),
        **context,
    }
    html = templates.get_template(name).render(**ctx)
    return HTMLResponse(html, status_code=status_code)
