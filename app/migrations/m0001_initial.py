"""0001：把最初的单表 posts 升级成完整结构，并保留已有文章。

老表结构（骨架版）：
    posts(id, title, content, created_at)
新表结构见 app/models.py。
"""
from __future__ import annotations

from sqlalchemy import Connection, inspect, text

from app.markdown_render import render_with_toc
from app.models import Base
from app.utils.text import excerpt, slugify

VERSION = 1


def _columns(conn: Connection, table: str) -> set[str]:
    return {col["name"] for col in inspect(conn).get_columns(table)}


def upgrade(conn: Connection) -> None:
    tables = set(inspect(conn).get_table_names())
    legacy = "posts" in tables and "slug" not in _columns(conn, "posts")

    if legacy:
        conn.execute(text("ALTER TABLE posts RENAME TO posts_legacy"))

    Base.metadata.create_all(conn)

    if not legacy:
        return

    rows = conn.execute(
        text("SELECT id, title, content, created_at FROM posts_legacy ORDER BY id")
    ).all()

    used_slugs: set[str] = set()
    for row in rows:
        title = (row.title or "").strip() or f"未命名文章 {row.id}"
        base = slugify(title) or f"post-{row.id}"
        slug = base
        suffix = 2
        while slug in used_slugs:
            slug = f"{base}-{suffix}"
            suffix += 1
        used_slugs.add(slug)

        content_md = row.content or ""
        content_html, _ = render_with_toc(content_md)
        created_at = row.created_at or "2026-01-01T00:00:00"
        # 老表的 created_at 是 naive UTC 字符串（datetime.utcnow），直接沿用
        conn.execute(
            text(
                """
                INSERT INTO posts
                    (id, slug, title, summary, content_md, content_html, cover_image,
                     status, views, created_at, updated_at, published_at)
                VALUES
                    (:id, :slug, :title, :summary, :md, :html, NULL,
                     'published', 0, :created_at, :updated_at, :published_at)
                """
            ),
            {
                "id": row.id,
                "slug": slug,
                "title": title,
                "summary": excerpt(content_md),
                "md": content_md,
                "html": content_html,
                "created_at": created_at,
                "updated_at": created_at,
                "published_at": created_at,
            },
        )

    conn.execute(text("DROP TABLE posts_legacy"))
