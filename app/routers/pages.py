"""前台 HTML 页面：首页、文章、标签、搜索。

页面直接调用 service 层拿数据（不绕一圈内部 HTTP），
API 路由只服务浏览器里的 JS 和以后可能的移动端。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import schemas
from app.config import settings
from app.database import get_db
from app.models import Post, PostStatus, Tag
from app.services import comments as comment_service
from app.services import posts as post_service
from app.templating import Pagination, page_url, render
from app.utils.timez import format_dt

router = APIRouter(tags=["pages"], include_in_schema=False)


def _published_count(db: Session) -> int:
    return db.execute(
        select(func.count(Post.id)).where(Post.status == PostStatus.PUBLISHED)
    ).scalar_one()


def _tag_cloud(db: Session) -> list[schemas.TagWithCount]:
    return post_service.list_tags(db)


def _list_page(
    request: Request,
    db: Session,
    *,
    page: int,
    base_path: str,
    template: str,
    heading: str | None = None,
    tag_slug: str | None = None,
    keyword: str | None = None,
) -> HTMLResponse:
    result = post_service.list_posts(
        db,
        page=page,
        page_size=settings.page_size,
        tag_slug=tag_slug,
        keyword=keyword,
    )
    pagination = Pagination(
        page=result.page,
        total_pages=result.total_pages,
        builder=lambda number: page_url(request, base_path, number),
    )
    return render(
        request,
        template,
        posts=[post_service.serialize_list_item(db, post) for post in result.items],
        pagination=pagination,
        total=result.total,
        heading=heading,
        keyword=keyword or "",
        tag_slug=tag_slug,
        tags=_tag_cloud(db),
    )


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    return _list_page(request, db, page=1, base_path="/", template="index.html")


@router.get("/page/{page}", response_class=HTMLResponse)
def home_page(request: Request, page: int, db: Session = Depends(get_db)):
    return _list_page(request, db, page=max(1, page), base_path="/", template="index.html")


@router.get("/tags", response_class=HTMLResponse)
def tags_index(request: Request, db: Session = Depends(get_db)):
    return render(request, "tags.html", tags=_tag_cloud(db), total=_published_count(db))


@router.get("/tag/{slug}", response_class=HTMLResponse)
def tag_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    tag = db.execute(select(Tag).where(Tag.slug == slug)).scalar_one_or_none()
    if tag is None:
        return render(request, "error.html", status_code=404, code=404, message="标签不存在")
    return _list_page(
        request,
        db,
        page=1,
        base_path=f"/tag/{slug}",
        template="index.html",
        heading=f"标签：{tag.name}",
        tag_slug=slug,
    )


@router.get("/tag/{slug}/page/{page}", response_class=HTMLResponse)
def tag_page(request: Request, slug: str, page: int, db: Session = Depends(get_db)):
    tag = db.execute(select(Tag).where(Tag.slug == slug)).scalar_one_or_none()
    if tag is None:
        return render(request, "error.html", status_code=404, code=404, message="标签不存在")
    return _list_page(
        request,
        db,
        page=max(1, page),
        base_path=f"/tag/{slug}",
        template="index.html",
        heading=f"标签：{tag.name}",
        tag_slug=slug,
    )


@router.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = Query("", max_length=100), db: Session = Depends(get_db)):
    keyword = q.strip()
    return _list_page(
        request,
        db,
        page=1,
        base_path="/search",
        template="search.html",
        heading=f"搜索：{keyword}" if keyword else "搜索",
        keyword=keyword or None,
    )


@router.get("/search/page/{page}", response_class=HTMLResponse)
def search_page(
    request: Request,
    page: int,
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
):
    keyword = q.strip()
    return _list_page(
        request,
        db,
        page=max(1, page),
        base_path="/search",
        template="search.html",
        heading=f"搜索：{keyword}" if keyword else "搜索",
        keyword=keyword or None,
    )


@router.get("/{slug}", response_class=HTMLResponse)
def post_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    post = post_service.get_post_by_slug(db, slug)
    if post is None or post.status != PostStatus.PUBLISHED:
        return render(request, "error.html", status_code=404, code=404, message="文章不存在")

    # 阅读量 +1：UPDATE 而非 ORM 赋值，避免并发丢更新
    db.execute(update(Post).where(Post.id == post.id).values(views=Post.views + 1))
    db.commit()
    db.refresh(post)

    prev_post, next_post = post_service.neighbors(db, post)
    return render(
        request,
        "post.html",
        post=post,
        toc=post.content_toc,
        prev=prev_post,
        next=next_post,
        comments=comment_service.list_approved_comments(db, post.id),
        published_date=format_dt(post.published_at or post.created_at),
        tags=_tag_cloud(db),
    )


def not_found(request: Request, message: str = "页面不存在") -> HTMLResponse:
    return render(request, "error.html", status_code=404, code=404, message=message)


def server_error(request: Request) -> HTMLResponse:
    return render(request, "error.html", status_code=500, code=500, message="服务器开小差了")


__all__ = ["router", "not_found", "server_error"]
