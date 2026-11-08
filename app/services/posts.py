"""文章相关的业务逻辑：slug、标签、CRUD、列表查询。"""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.markdown_render import render_inline, render_with_toc
from app.models import Comment, Post, PostStatus, Tag
from app.utils.text import excerpt, slugify, unique_slug


class PostConflict(Exception):
    """slug 冲突等可预期的业务错误。"""


@dataclass
class PageResult:
    items: list[Post]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total / self.page_size)) if self.total else 0

    def meta(self) -> schemas.PageMeta:
        return schemas.PageMeta(
            page=self.page,
            page_size=self.page_size,
            total=self.total,
            total_pages=self.total_pages,
        )


# ------------------------------------------------------------------ 标签
def normalize_tag_names(names: list[str]) -> list[str]:
    """去空、去重、保序，最多 8 个。"""
    seen: set[str] = set()
    result: list[str] = []
    for raw in names or []:
        name = (raw or "").strip().lstrip("#")
        if not name or len(name) > 30:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
    return result[:8]


def resolve_tags(db: Session, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for name in normalize_tag_names(names):
        tag_slug = slugify(name) or f"tag-{abs(hash(name)) % 100000}"
        tag = db.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
        if tag is None:
            tag = db.execute(select(Tag).where(Tag.slug == tag_slug)).scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name, slug=tag_slug)
            db.add(tag)
        tags.append(tag)
    return tags


# ------------------------------------------------------------------ slug
def slug_taken(db: Session, candidate: str, exclude_id: int | None = None) -> bool:
    stmt = select(Post.id).where(Post.slug == candidate)
    if exclude_id is not None:
        stmt = stmt.where(Post.id != exclude_id)
    return db.execute(stmt).first() is not None


def build_slug(db: Session, desired: str | None, title: str, exclude_id: int | None = None) -> str:
    base = slugify(desired or "") or slugify(title) or "post"
    return unique_slug(base, lambda s: slug_taken(db, s, exclude_id), fallback="post")


# ------------------------------------------------------------------ 写
def _apply_content(post: Post, content_md: str) -> None:
    """渲染 Markdown 并存 HTML + 目录；摘要为空时自动生成。"""
    html, toc = render_with_toc(content_md)
    post.content_md = content_md
    post.content_html = html
    post.content_toc = toc
    if not (post.summary or "").strip():
        post.summary = excerpt(content_md)


def create_post(db: Session, payload: schemas.PostCreate) -> Post:
    post = Post(
        slug=build_slug(db, payload.slug, payload.title),
        title=payload.title.strip(),
        summary=payload.summary.strip(),
        cover_image=payload.cover_image or None,
        status=payload.status,
        tags=resolve_tags(db, payload.tags),
    )
    _apply_content(post, payload.content_md)
    if post.status == PostStatus.PUBLISHED:
        post.published_at = models.utcnow()
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def update_post(db: Session, post: Post, payload: schemas.PostUpdate) -> Post:
    data = payload.model_dump(exclude_unset=True)

    if "slug" in data and data["slug"]:
        post.slug = build_slug(db, data["slug"], data.get("title") or post.title, exclude_id=post.id)
    if "title" in data and data["title"]:
        post.title = data["title"].strip()
    if "summary" in data:
        post.summary = (data["summary"] or "").strip()
    if "cover_image" in data:
        post.cover_image = data["cover_image"] or None
    if "content_md" in data and data["content_md"] is not None:
        _apply_content(post, data["content_md"])
    if "tags" in data and data["tags"] is not None:
        post.tags = resolve_tags(db, data["tags"])

    if "status" in data and data["status"]:
        if data["status"] not in PostStatus.ALL:
            raise PostConflict("非法状态")
        if data["status"] == PostStatus.PUBLISHED and post.published_at is None:
            post.published_at = models.utcnow()
        if data["status"] == PostStatus.DRAFT:
            post.published_at = None
        post.status = data["status"]

    db.commit()
    db.refresh(post)
    return post


def delete_post(db: Session, post: Post) -> None:
    db.delete(post)
    db.commit()


# ------------------------------------------------------------------ 读
def _comment_counts(db: Session, post_ids: list[int]) -> dict[int, int]:
    if not post_ids:
        return {}
    rows = db.execute(
        select(Comment.post_id, func.count(Comment.id))
        .where(Comment.post_id.in_(post_ids), Comment.status == "approved")
        .group_by(Comment.post_id)
    ).all()
    return {post_id: count for post_id, count in rows}


def list_posts(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 10,
    tag_slug: str | None = None,
    keyword: str | None = None,
    status: str | None = PostStatus.PUBLISHED,
    include_drafts: bool = False,
) -> PageResult:
    page = max(1, page)
    page_size = max(1, min(page_size, 50))

    stmt = select(Post).options(selectinload(Post.tags))

    if include_drafts:
        if status in PostStatus.ALL:
            stmt = stmt.where(Post.status == status)
    else:
        stmt = stmt.where(Post.status == PostStatus.PUBLISHED)

    if tag_slug:
        stmt = stmt.join(Post.tags).where(Tag.slug == tag_slug)

    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Post.title.like(like), Post.summary.like(like)))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    ordering = func.coalesce(Post.published_at, Post.created_at).desc()
    rows = db.execute(
        stmt.order_by(ordering).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return PageResult(
        items=list(rows), total=total, page=page, page_size=page_size
    )


def get_post_by_slug(db: Session, slug: str) -> Post | None:
    return db.execute(
        select(Post).options(selectinload(Post.tags)).where(Post.slug == slug)
    ).scalar_one_or_none()


def get_post_by_id(db: Session, post_id: int) -> Post | None:
    return db.execute(
        select(Post).options(selectinload(Post.tags)).where(Post.id == post_id)
    ).scalar_one_or_none()


def neighbors(db: Session, post: Post) -> tuple[Post | None, Post | None]:
    """按发布时间取上一篇 / 下一篇（仅已发布）。"""
    anchor = post.published_at or post.created_at

    prev_post = db.execute(
        select(Post)
        .where(Post.status == PostStatus.PUBLISHED, Post.id != post.id,
               func.coalesce(Post.published_at, Post.created_at) < anchor)
        .order_by(func.coalesce(Post.published_at, Post.created_at).desc())
        .limit(1)
    ).scalar_one_or_none()

    next_post = db.execute(
        select(Post)
        .where(Post.status == PostStatus.PUBLISHED, Post.id != post.id,
               func.coalesce(Post.published_at, Post.created_at) > anchor)
        .order_by(func.coalesce(Post.published_at, Post.created_at).asc())
        .limit(1)
    ).scalar_one_or_none()

    return prev_post, next_post


def list_tags(db: Session) -> list[schemas.TagWithCount]:
    rows = db.execute(
        select(Tag, func.count(Post.id))
        .join(Tag.posts)
        .where(Post.status == PostStatus.PUBLISHED)
        .group_by(Tag.id)
        .order_by(func.count(Post.id).desc(), Tag.name.asc())
    ).all()
    return [
        schemas.TagWithCount(id=tag.id, name=tag.name, slug=tag.slug, post_count=count)
        for tag, count in rows
    ]


def serialize_list_item(db: Session, post: Post, counts: dict[int, int] | None = None) -> schemas.PostListItem:
    counts = counts if counts is not None else _comment_counts(db, [post.id])
    return schemas.PostListItem(
        id=post.id,
        slug=post.slug,
        title=post.title,
        title_html=render_inline(post.title),
        summary=post.summary,
        cover_image=post.cover_image,
        status=post.status,
        views=post.views,
        created_at=post.created_at,
        updated_at=post.updated_at,
        published_at=post.published_at,
        tags=[schemas.TagOut.model_validate(t) for t in post.tags],
        comment_count=counts.get(post.id, 0),
    )


def serialize_page(db: Session, result: PageResult) -> schemas.PostPage:
    counts = _comment_counts(db, [p.id for p in result.items])
    return schemas.PostPage(
        items=[serialize_list_item(db, p, counts) for p in result.items],
        meta=result.meta(),
    )
