"""核心链路测试：鉴权、发文、评论审核、图片上传、公开页面。

只测真正会坏的地方，不追覆盖率（30 项细节留给 scripts/smoke_test.py）。
"""
from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


def test_admin_requires_login_and_csrf(client):
    assert client.get("/api/admin/posts").status_code == 401

    login = client.post(
        "/api/admin/login", json={"username": "admin", "password": "test-password"}
    )
    assert login.status_code == 200
    assert client.cookies.get("blog_admin_csrf")

    # 有登录 cookie，但没有 CSRF 头
    response = client.post("/api/admin/posts", json={"title": "x", "status": "draft"})
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_wrong_password_is_401(client):
    response = client.post(
        "/api/admin/login", json={"username": "admin", "password": "wrong"}
    )
    assert response.status_code == 401


def test_create_post_renders_markdown_and_slugifies_chinese(client, login):
    response = client.post(
        "/api/admin/posts",
        headers=login,
        json={
            "title": "我的第一篇技术文章",
            "content_md": "## 标题\n\n```python\nprint('hi')\n```\n",
            "tags": ["Python", "测试"],
            "status": "published",
        },
    )
    assert response.status_code == 201, response.text
    post = response.json()

    assert post["slug"] == "wo-de-di-yi-pian-ji-shu-wen-zhang"
    assert "<h2" in post["content_html"]
    assert "codehilite" in post["content_html"]
    assert [tag["name"] for tag in post["tags"]] == ["Python", "测试"]

    page = client.get(f"/{post['slug']}")
    assert page.status_code == 200
    assert "我的第一篇技术文章" in page.text
    assert "目录" in page.text          # 有 h2 时详情页渲染 TOC


def test_draft_hidden_from_public(client, login):
    created = client.post(
        "/api/admin/posts",
        headers=login,
        json={"title": "草稿文章", "content_md": "还没写完", "status": "draft"},
    ).json()
    assert client.get(f"/{created['slug']}").status_code == 404
    assert client.get(f"/api/posts/{created['slug']}").status_code == 404


def test_comment_needs_approval(client, published_post):
    slug = published_post["slug"]
    submitted = client.post(
        f"/api/posts/{slug}/comments",
        json={
            "author_name": "路人",
            "content": "测试评论内容",
            "captcha_id": "whatever",
            "captcha_answer": "abcd",
        },
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["pending"] is True

    # 待审评论前台看不到
    assert client.get(f"/api/posts/{slug}/comments").json() == []

    # 后台审核通过
    login = client.post(
        "/api/admin/login", json={"username": "admin", "password": "test-password"}
    )
    csrf = client.cookies.get("blog_admin_csrf")
    pending = client.get("/api/admin/comments?status=pending").json()["items"]
    comment = next(item for item in pending if item["post_slug"] == slug)
    approved = client.post(
        f"/api/admin/comments/{comment['id']}/approve", headers={"X-CSRF-Token": csrf}
    )
    assert approved.status_code == 200

    visible = client.get(f"/api/posts/{slug}/comments").json()
    assert [item["author_name"] for item in visible] == ["路人"]


def test_image_upload_converts_to_webp(client, login):
    buffer = io.BytesIO()
    Image.new("RGB", (2400, 1200), (230, 120, 30)).save(buffer, format="PNG")
    buffer.seek(0)

    response = client.post(
        "/api/admin/media",
        headers=login,
        files={"file": ("upload.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 200, response.text
    media = response.json()

    assert media["url"].endswith(".webp")
    assert media["width"] == 1920          # 限宽生效
    assert media["thumb_url"].endswith("_thumb.webp")
    assert client.get(media["url"]).status_code == 200
    assert client.get(media["thumb_url"]).status_code == 200


def test_non_image_upload_rejected(client, login):
    response = client.post(
        "/api/admin/media",
        headers=login,
        files={"file": ("evil.html", b"<script>alert(1)</script>", "text/html")},
    )
    assert response.status_code == 400


def test_public_pages_and_404(client, published_post):
    for path in ["/", "/tags", "/rss.xml", "/sitemap.xml", "/robots.txt"]:
        response = client.get(path)
        assert response.status_code == 200, path

    assert client.get("/rss.xml").headers["content-type"].startswith("application/rss+xml")

    missing = client.get("/no-such-post-here")
    assert missing.status_code == 404
    assert "text/html" in missing.headers["content-type"]

    # 未登录访问后台页面跳到登录
    fresh = TestClient(app)
    redirect = fresh.get("/admin", follow_redirects=False)
    assert redirect.status_code == 303
    assert "/admin/login" in redirect.headers["location"]
