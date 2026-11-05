"""RSS 与 sitemap：给订阅器和搜索引擎用。"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Post, PostStatus, Tag
from app.utils.timez import to_local

router = APIRouter(tags=["feeds"], include_in_schema=False)

_RSS_HEADERS = {"Cache-Control": "public, max-age=600"}


def _post_link(slug: str) -> str:
    return f"{settings.site_url}/{slug}"


def _cdata(html: str) -> str:
    """CDATA 里不能出现 ]]>，出现时拆成两段。"""
    return "<![CDATA[" + html.replace("]]>", "]]]]><![CDATA[>") + "]]>"


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
        categories = "".join(
            f"\n      <category>{escape(tag.name)}</category>" for tag in post.tags
        )
        items.append(
            f"""    <item>
      <title>{escape(post.title)}</title>
      <link>{_post_link(post.slug)}</link>
      <guid isPermaLink="true">{_post_link(post.slug)}</guid>
      <pubDate>{format_datetime(when) if when else ''}</pubDate>
      <dc:creator>{escape(settings.site_author)}</dc:creator>
      <description>{escape(post.summary)}</description>{categories}
      <content:encoded>{_cdata(post.content_html)}</content:encoded>
    </item>"""
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>{escape(settings.site_name)}</title>
    <link>{base}/</link>
    <description>{escape(settings.site_description)}</description>
    <language>zh-CN</language>
    <generator>{escape(settings.site_name)}</generator>
    <lastBuildDate>{format_datetime(to_local(datetime.now(timezone.utc)))}</lastBuildDate>
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
    latest = None
    for post in posts:
        when = to_local(post.published_at or post.created_at)
        if when and (latest is None or when > latest):
            latest = when
    home_mod = f"<lastmod>{latest.date().isoformat()}</lastmod>" if latest else ""
    urls = [
        f"  <url><loc>{base}/</loc>{home_mod}</url>",
        f"  <url><loc>{base}/tags</loc>{home_mod}</url>",
    ]

    for post in posts:
        when = to_local(post.published_at or post.created_at)
        lastmod = f"<lastmod>{when.date().isoformat()}</lastmod>" if when else ""
        urls.append(f"  <url><loc>{base}/{post.slug}</loc>{lastmod}</url>")

    tags = (
        db.execute(
            select(Tag)
            .join(Tag.posts)
            .where(Post.status == PostStatus.PUBLISHED)
            .distinct()
            .order_by(Tag.name)
        )
        .scalars()
        .all()
    )
    for tag in tags:
        whens = [
            to_local(p.published_at or p.created_at)
            for p in tag.posts
            if p.status == PostStatus.PUBLISHED
        ]
        whens = [w for w in whens if w]
        tag_mod = f"<lastmod>{max(whens).date().isoformat()}</lastmod>" if whens else ""
        urls.append(f"  <url><loc>{base}/tag/{tag.slug}</loc>{tag_mod}</url>")

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


@router.get("/.well-known/security.txt")
def security_txt() -> Response:
    body = (
        f"Contact: mailto:{settings.site_email}\n"
        "Expires: 2027-11-05T00:00:00.000Z\n"
        "Preferred-Languages: zh-CN, en\n"
        f"Canonical: {settings.site_url}/.well-known/security.txt\n"
    )
    return Response(body, media_type="text/plain; charset=utf-8", headers=_RSS_HEADERS)
