"""评论业务：提交校验（蜜罐 → 验证码 → 父评论 → 限流）、审核、树形展示。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.captcha import captcha_store
from app.config import settings
from app.models import Comment, CommentStatus, Post
from app.ratelimit import rate_limiter


class CommentRejected(Exception):
    """评论被拒，消息直接展示给用户。"""


def _touch_rate_limit(ip: str) -> None:
    """两个窗口都通过才记账，避免被小时限制拒绝时污染 30 秒窗口。"""
    wait_short = rate_limiter.peek(f"c:{ip}:60", settings.comment_rate_seconds, 1)
    wait_hour = rate_limiter.peek(f"c:{ip}:3600", 3600, settings.comment_rate_per_hour)
    if wait_short > 0:
        raise CommentRejected(f"评论太频繁，请 {int(wait_short) + 1} 秒后再试")
    if wait_hour > 0:
        raise CommentRejected("单位时间内评论过多，请稍后再试")
    rate_limiter.check(f"c:{ip}:60", settings.comment_rate_seconds, 1)
    rate_limiter.check(f"c:{ip}:3600", 3600, settings.comment_rate_per_hour)


def submit_comment(
    db: Session,
    post: Post,
    payload: schemas.CommentCreate,
    *,
    ip: str,
    user_agent: str,
) -> Comment:
    # 1) 蜜罐：正常浏览器里这个字段是隐藏的，被填 = 机器人
    if (payload.website or "").strip():
        raise CommentRejected("提交失败")

    # 2) 验证码（一次性消费）；先验码再限流，输错验证码不会把用户锁 60 秒。
    #    但验码前要有宽松的总次数限制，防止绕过“成功才计数”暴力试码。
    if rate_limiter.check(f"c:{ip}:attempts", 3600, settings.comment_attempts_per_hour) > 0:
        raise CommentRejected("尝试次数过多，请稍后再试")
    if not captcha_store.verify(payload.captcha_id, payload.captcha_answer):
        raise CommentRejected("验证码错误或已过期，请换一张")

    # 3) 父评论校验：必须属于同一篇文章、已通过、且是顶层评论（只允许一层回复）
    parent_id = payload.parent_id
    if parent_id is not None:
        parent = db.get(Comment, parent_id)
        if parent is None or parent.post_id != post.id or parent.status != CommentStatus.APPROVED:
            raise CommentRejected("回复的评论不存在")
        parent_id = parent.parent_id or parent.id  # 二级回复挂到顶层，保持两层结构

    # 4) 限流只统计真正要入库的评论
    _touch_rate_limit(ip)

    status = (
        CommentStatus.PENDING if settings.comment_require_approval else CommentStatus.APPROVED
    )
    comment = Comment(
        post_id=post.id,
        parent_id=parent_id,
        author_name=payload.author_name,
        content=payload.content,
        status=status,
        ip=ip,
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def list_approved_comments(db: Session, post_id: int) -> list[schemas.CommentOut]:
    """取已通过的评论，组装成两层结构。"""
    rows = db.execute(
        select(Comment)
        .where(Comment.post_id == post_id, Comment.status == CommentStatus.APPROVED)
        .order_by(Comment.created_at.asc())
    ).scalars().all()

    roots: dict[int, schemas.CommentOut] = {}
    for row in rows:
        if row.parent_id is None:
            roots[row.id] = schemas.CommentOut(
                id=row.id,
                author_name=row.author_name,
                content=row.content,
                created_at=row.created_at,
                parent_id=None,
                replies=[],
            )
    for row in rows:
        if row.parent_id is not None and row.parent_id in roots:
            roots[row.parent_id].replies.append(
                schemas.CommentOut(
                    id=row.id,
                    author_name=row.author_name,
                    content=row.content,
                    created_at=row.created_at,
                    parent_id=row.parent_id,
                    replies=[],
                )
            )
    return list(roots.values())


def count_pending(db: Session) -> int:
    return db.query(Comment).filter(Comment.status == CommentStatus.PENDING).count()
