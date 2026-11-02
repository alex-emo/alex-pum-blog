"""RSS 与 sitemap：给订阅器和搜索引擎用。"""
from __future__ import annotations

from email.utils import format_datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Post, PostStatus
from app.utils.timez import to_local

router = APIRouter(tags=["feeds"], include_in_schema=False)

_RSS_HEADERS = {"Cache-Control": "public, max-age=600"}


def _published_posts(db: Session, limit: int | None = None) -> list[Post]:
    stmt = (
        select(Post)
        .where(Post.status == PostStatus.PUBLISHED)
        .order_by(Post.published_at.desc(), Post.created_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


@router.get("/rss.xml")
def rss(db: Session = Depends(get_db)) -> Response:
    posts = _published_posts(db, limit=20)
    base = settings.site_url
    items: list[str] = []
    for post in posts:
        when = to_local(post.published_at or post.created_at)
        items.append(
            f"""    <item>
      <title>{escape(post.title)}</title>
      <link>{base}/{post.slug}</link>
      <guid isPermaLink="true">{base}/{post.slug}</guid>
      <pubDate>{format_datetime(when) if when else ''}</pubDate>
      <description>{escape(post.summary)}</description>
    </item>"""
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(settings.site_name)}</title>
    <link>{base}/</link>
    <description>{escape(settings.site_description)}</description>
    <language>zh-CN</language>
    <atom:link href="{base}/rss.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>
"""
    return Response(xml, media_type="application/rss+xml; charset=utf-8", headers=_RSS_HEADERS)


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)) -> Response:
    posts = _published_posts(db)
    base = settings.site_url
    urls = [f"  <url><loc>{base}/</loc></url>", f"  <url><loc>{base}/tags</loc></url>"]

    for post in posts:
        when = to_local(post.published_at or post.created_at)
        lastmod = f"<lastmod>{when.date().isoformat()}</lastmod>" if when else ""
        urls.append(f"  <url><loc>{base}/{post.slug}</loc>{lastmod}</url>")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
"""
    return Response(xml, media_type="application/xml; charset=utf-8", headers=_RSS_HEADERS)


@router.get("/robots.txt")
def robots() -> Response:
    return Response(
        f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {settings.site_url}/sitemap.xml\n",
        media_type="text/plain; charset=utf-8",
        headers=_RSS_HEADERS,
    )
