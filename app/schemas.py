"""请求 / 响应模型（Pydantic v2）。

命名约定：
- *Create / *Update 是入参
- *Out 是出参
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ====================================================================== 标签
class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


class TagWithCount(TagOut):
    post_count: int = 0


# ====================================================================== 文章
class PostBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content_md: str = ""
    summary: str = Field(default="", max_length=500)
    cover_image: str | None = Field(default=None, max_length=300)
    status: str = "draft"


class PostCreate(PostBase):
    tags: list[str] = Field(default_factory=list)
    slug: str | None = Field(default=None, max_length=200)

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        if value not in {"draft", "published"}:
            raise ValueError("status 只能是 draft 或 published")
        return value


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content_md: str | None = None
    summary: str | None = Field(default=None, max_length=500)
    cover_image: str | None = Field(default=None, max_length=300)
    status: str | None = None
    tags: list[str] | None = None
    slug: str | None = Field(default=None, max_length=200)


class PostListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    summary: str
    cover_image: str | None
    status: str
    views: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    tags: list[TagOut] = Field(default_factory=list)
    comment_count: int = 0


class PostDetail(PostListItem):
    content_html: str = ""


class PostAdminDetail(PostDetail):
    content_md: str = ""


class PostNeighbor(BaseModel):
    slug: str
    title: str


class PostDetailWithNeighbors(BaseModel):
    post: PostDetail
    prev: PostNeighbor | None = None
    next: PostNeighbor | None = None


# ====================================================================== 分页
class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class PostPage(BaseModel):
    items: list[PostListItem]
    meta: PageMeta


# ====================================================================== 评论
class CommentCreate(BaseModel):
    author_name: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=2, max_length=2000)
    captcha_id: str = Field(min_length=1, max_length=64)
    captcha_answer: str = Field(min_length=1, max_length=10)
    parent_id: int | None = None
    # 蜜罐：正常用户看不到这个字段，机器人会填
    website: str = ""

    @field_validator("author_name", "content")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_name: str
    content: str
    created_at: datetime
    parent_id: int | None = None
    replies: list["CommentOut"] = Field(default_factory=list)


class CommentAdminOut(CommentOut):
    post_id: int
    post_title: str = ""
    post_slug: str = ""
    status: str
    ip: str | None = None


class CommentPage(BaseModel):
    """后台评论列表：带文章信息和状态。"""

    items: list[CommentAdminOut]
    meta: PageMeta


class CommentSubmitResult(BaseModel):
    ok: bool
    message: str
    pending: bool = False


# ====================================================================== 管理员
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    last_login_at: datetime | None = None


class LoginResult(BaseModel):
    admin: AdminOut
    csrf_token: str


# ====================================================================== 上传
class MediaOut(BaseModel):
    url: str
    thumb_url: str
    width: int
    height: int


# ====================================================================== 预览
class MarkdownPreview(BaseModel):
    content_md: str = ""


class MarkdownPreviewOut(BaseModel):
    html: str


# ====================================================================== 统计
class AdminStats(BaseModel):
    posts_total: int
    posts_published: int
    posts_draft: int
    comments_pending: int
    comments_total: int
    views_total: int
