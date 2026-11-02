"""0002：给文章加 content_toc（渲染时一并生成的目录 HTML）。

目录只在文章页用，每次请求重新跑 Markdown 不值当，
保存文章时和 HTML 一起生成、一起入库。
"""
from __future__ import annotations

from sqlalchemy import Connection, inspect, text

from app.markdown_render import render_with_toc

VERSION = 2


def upgrade(conn: Connection) -> None:
    columns = {col["name"] for col in inspect(conn).get_columns("posts")}
    if "content_toc" not in columns:
        conn.execute(text("ALTER TABLE posts ADD COLUMN content_toc TEXT NOT NULL DEFAULT ''"))

    # 回填已有文章的目录
    rows = conn.execute(text("SELECT id, content_md FROM posts")).all()
    for row in rows:
        _html, toc = render_with_toc(row.content_md or "")
        conn.execute(
            text("UPDATE posts SET content_toc = :toc WHERE id = :id"),
            {"toc": toc, "id": row.id},
        )
