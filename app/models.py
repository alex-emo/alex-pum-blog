"""数据表定义。

四张表：posts / tags / post_tags / comments / admin_users。
时间统一存 **naive UTC**（SQLite 没有时区概念），展示时按 SITE_TIMEZONE 转换。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """统一的时间来源：naive UTC。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


# 文章 <-> 标签 多对多
post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class PostStatus:
    """用字符串而不是 Python Enum，SQLite 里方便直接看、也方便以后加状态。"""

    DRAFT = "draft"
    PUBLISHED = "published"
    ALL = (DRAFT, PUBLISHED)


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500), default="")
    content_md: Mapped[str] = mapped_column(Text, default="")
    # 发布/保存时预先渲染好的 HTML 和目录，读的时候不再跑一遍 Markdown
    content_html: Mapped[str] = mapped_column(Text, default="")
    content_toc: Mapped[str] = mapped_column(Text, default="")
    cover_image: Mapped[str | None] = mapped_column(String(300), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default=PostStatus.DRAFT, index=True)
    views: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    tags: Mapped[list["Tag"]] = relationship(
        secondary=post_tags, back_populates="posts", lazy="selectin"
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_posts_status_published", "status", "published_at"),
    )

    @property
    def is_published(self) -> bool:
        return self.status == PostStatus.PUBLISHED


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    posts: Mapped[list[Post]] = relationship(secondary=post_tags, back_populates="tags")


class CommentStatus:
    PENDING = "pending"    # 待审核
    APPROVED = "approved"  # 已通过，前台可见
    SPAM = "spam"          # 垃圾/拒绝
    ALL = (PENDING, APPROVED, SPAM)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    # 一层回复：parent 是一条已通过的顶层评论
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, index=True
    )

    author_name: Mapped[str] = mapped_column(String(60))
    # 只收集展示用昵称，不收集邮箱/网站，减少隐私负担
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default=CommentStatus.PENDING, index=True
    )

    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    post: Mapped[Post] = relationship(back_populates="comments")
    replies: Mapped[list["Comment"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", passive_deletes=True
    )
    parent: Mapped["Comment | None"] = relationship(
        back_populates="replies", remote_side="Comment.id"
    )


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
