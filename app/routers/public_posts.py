"""公开文章接口：列表、详情、标签。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import schemas
from app.config import settings
from app.database import get_db
from app.models import Post, PostStatus
from app.services import posts as post_service

router = APIRouter(prefix="/api", tags=["posts"])


def _published_or_404(db: Session, slug: str) -> Post:
    post = post_service.get_post_by_slug(db, slug)
    if post is None or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="文章不存在")
    return post


@router.get("/posts", response_model=schemas.PostPage)
def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(0, ge=0, le=50, description="0 表示用站点默认值"),
    tag: str | None = Query(None, max_length=80),
    q: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
):
    result = post_service.list_posts(
        db,
        page=page,
        page_size=page_size or settings.page_size,
        tag_slug=tag,
        keyword=q,
    )
    return post_service.serialize_page(db, result)


@router.get("/posts/{slug}", response_model=schemas.PostDetailWithNeighbors)
def get_post(slug: str, db: Session = Depends(get_db)):
    post = _published_or_404(db, slug)

    # 阅读量 +1：用 UPDATE 而不是 ORM 属性赋值，避免并发下丢失更新
    db.execute(update(Post).where(Post.id == post.id).values(views=Post.views + 1))
    db.commit()
    db.refresh(post)

    prev_post, next_post = post_service.neighbors(db, post)
    detail = post_service.serialize_list_item(db, post)
    return schemas.PostDetailWithNeighbors(
        post=schemas.PostDetail(**detail.model_dump(), content_html=post.content_html),
        prev=schemas.PostNeighbor(slug=prev_post.slug, title=prev_post.title) if prev_post else None,
        next=schemas.PostNeighbor(slug=next_post.slug, title=next_post.title) if next_post else None,
    )


@router.get("/tags", response_model=list[schemas.TagWithCount])
def list_tags(db: Session = Depends(get_db)):
    return post_service.list_tags(db)


@router.get("/stats")
def public_stats(db: Session = Depends(get_db)):
    """给前台显示"共 N 篇文章"。"""
    total = db.execute(
        select(func.count(Post.id)).where(Post.status == PostStatus.PUBLISHED)
    ).scalar_one()
    return {"posts": total}
