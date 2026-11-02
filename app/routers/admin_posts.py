"""管理员文章接口：CRUD、状态、统计。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin, require_admin_csrf
from app.markdown_render import render_with_toc
from app.models import Comment, CommentStatus, Post, PostStatus
from app.services import posts as post_service

router = APIRouter(prefix="/api/admin", tags=["admin-posts"])


def _serialize_admin_detail(db: Session, post: Post) -> schemas.PostAdminDetail:
    base = post_service.serialize_list_item(db, post)
    return schemas.PostAdminDetail(
        **base.model_dump(),
        content_html=post.content_html,
        content_md=post.content_md,
    )


def _get_or_404(db: Session, post_id: int) -> Post:
    post = post_service.get_post_by_id(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    return post


@router.post("/preview", response_model=schemas.MarkdownPreviewOut)
def preview_markdown(
    payload: schemas.MarkdownPreview,
    admin: models.AdminUser = Depends(require_admin),
):
    """编辑器实时预览用：走和正文相同的渲染管线。"""
    html, _toc = render_with_toc(payload.content_md)
    return schemas.MarkdownPreviewOut(html=html)


@router.get("/posts", response_model=schemas.PostPage)
def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    q: str | None = Query(None, max_length=100),
    admin: models.AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = post_service.list_posts(
        db,
        page=page,
        page_size=page_size,
        keyword=q,
        status=status_filter,
        include_drafts=True,
    )
    return post_service.serialize_page(db, result)


@router.post("/posts", response_model=schemas.PostAdminDetail, status_code=201)
def create_post(
    payload: schemas.PostCreate,
    admin: models.AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    if payload.status == PostStatus.PUBLISHED and not (payload.title and payload.content_md):
        raise HTTPException(status_code=400, detail="发布前需要标题和正文")
    post = post_service.create_post(db, payload)
    return _serialize_admin_detail(db, post)


@router.get("/posts/{post_id}", response_model=schemas.PostAdminDetail)
def get_post(
    post_id: int,
    admin: models.AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _serialize_admin_detail(db, _get_or_404(db, post_id))


@router.patch("/posts/{post_id}", response_model=schemas.PostAdminDetail)
def update_post(
    post_id: int,
    payload: schemas.PostUpdate,
    admin: models.AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    post = _get_or_404(db, post_id)
    updated = post_service.update_post(db, post, payload)
    return _serialize_admin_detail(db, updated)


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: int,
    admin: models.AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    post = _get_or_404(db, post_id)
    post_service.delete_post(db, post)
    return {"ok": True}


@router.get("/stats", response_model=schemas.AdminStats)
def stats(
    admin: models.AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    def count_posts(status: str | None = None) -> int:
        stmt = select(func.count(Post.id))
        if status:
            stmt = stmt.where(Post.status == status)
        return db.execute(stmt).scalar_one()

    return schemas.AdminStats(
        posts_total=count_posts(),
        posts_published=count_posts(PostStatus.PUBLISHED),
        posts_draft=count_posts(PostStatus.DRAFT),
        comments_pending=db.execute(
            select(func.count(Comment.id)).where(Comment.status == CommentStatus.PENDING)
        ).scalar_one(),
        comments_total=db.execute(select(func.count(Comment.id))).scalar_one(),
        views_total=db.execute(select(func.coalesce(func.sum(Post.views), 0))).scalar_one(),
    )
