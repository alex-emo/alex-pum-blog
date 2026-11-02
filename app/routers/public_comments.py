"""公开评论接口：验证码下发、评论读取、评论提交。"""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import schemas
from app.captcha import captcha_store
from app.database import get_db
from app.deps import client_ip
from app.models import CommentStatus, PostStatus
from app.ratelimit import rate_limiter
from app.services import comments as comment_service
from app.services import posts as post_service

router = APIRouter(prefix="/api", tags=["comments"])


@router.get("/captcha")
def get_captcha(request: Request) -> dict:
    # 验证码要画图，挡住无脑刷接口的请求
    if rate_limiter.check(f"captcha:{client_ip(request)}", 60, 60) > 0:
        raise HTTPException(status_code=429, detail="验证码请求过于频繁，请稍后再试")
    captcha_id, png = captcha_store.issue()
    encoded = base64.b64encode(png).decode()
    return {"captcha_id": captcha_id, "image": f"data:image/png;base64,{encoded}"}


@router.get("/posts/{slug}/comments", response_model=list[schemas.CommentOut])
def list_comments(slug: str, db: Session = Depends(get_db)):
    post = post_service.get_post_by_slug(db, slug)
    if post is None or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="文章不存在")
    return comment_service.list_approved_comments(db, post.id)


@router.post("/posts/{slug}/comments", response_model=schemas.CommentSubmitResult)
def create_comment(
    slug: str,
    payload: schemas.CommentCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    post = post_service.get_post_by_slug(db, slug)
    if post is None or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="文章不存在")

    try:
        comment = comment_service.submit_comment(
            db,
            post,
            payload,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
    except comment_service.CommentRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if comment.status == CommentStatus.PENDING:
        return schemas.CommentSubmitResult(
            ok=True, message="评论已提交，审核通过后显示", pending=True
        )
    return schemas.CommentSubmitResult(ok=True, message="评论成功")
