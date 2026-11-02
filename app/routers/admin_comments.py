"""管理员评论接口：待审列表、通过、标记垃圾、删除。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin, require_admin_csrf
from app.models import Comment, CommentStatus, Post
from app.services.posts import PageResult

router = APIRouter(prefix="/api/admin", tags=["admin-comments"])


def _get_or_404(db: Session, comment_id: int) -> Comment:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="评论不存在")
    return comment


def _serialize(db: Session, comment: Comment, post_map: dict[int, Post]) -> schemas.CommentAdminOut:
    post = post_map.get(comment.post_id)
    return schemas.CommentAdminOut(
        id=comment.id,
        author_name=comment.author_name,
        content=comment.content,
        created_at=comment.created_at,
        parent_id=comment.parent_id,
        post_id=comment.post_id,
        post_title=post.title if post else "",
        post_slug=post.slug if post else "",
        status=comment.status,
        ip=comment.ip,
    )


@router.get("/comments", response_model=schemas.CommentPage)
def list_comments(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: models.AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(Comment).order_by(Comment.created_at.desc())
    if status_filter:
        if status_filter not in CommentStatus.ALL:
            raise HTTPException(status_code=400, detail="非法状态")
        stmt = stmt.where(Comment.status == status_filter)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()

    post_ids = {c.post_id for c in rows}
    post_map = (
        {p.id: p for p in db.execute(select(Post).where(Post.id.in_(post_ids))).scalars().all()}
        if post_ids else {}
    )

    meta = PageResult(items=[], total=total, page=page, page_size=page_size).meta()
    return schemas.CommentPage(
        items=[_serialize(db, c, post_map) for c in rows], meta=meta
    )


@router.post("/comments/{comment_id}/approve")
def approve(
    comment_id: int,
    admin: models.AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    comment = _get_or_404(db, comment_id)
    comment.status = CommentStatus.APPROVED
    db.commit()
    return {"ok": True, "status": comment.status}


@router.post("/comments/{comment_id}/spam")
def mark_spam(
    comment_id: int,
    admin: models.AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    comment = _get_or_404(db, comment_id)
    comment.status = CommentStatus.SPAM
    db.commit()
    return {"ok": True, "status": comment.status}


@router.delete("/comments/{comment_id}")
def delete(
    comment_id: int,
    admin: models.AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    comment = _get_or_404(db, comment_id)
    db.delete(comment)
    db.commit()
    return {"ok": True}
