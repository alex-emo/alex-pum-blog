"""冒烟测试：跑一遍关键链路，不追求覆盖率，只保证主流程没断。

用法：venv/bin/python -m scripts.smoke_test
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.captcha import captcha_store  # noqa: E402
from app.main import app  # noqa: E402

USERNAME = "admin"
PASSWORD = "12141327Alex"

# 冒烟测试放过验证码这一步（验证码本身单独校验）
captcha_store.verify = lambda captcha_id, answer: True  # type: ignore[method-assign]

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name} {detail}")
        failures.append(name)


def main() -> int:
    client = TestClient(app)

    print("[1] 健康检查")
    health = client.get("/api/health")
    check("GET /api/health", health.status_code == 200, health.text)

    print("[2] 公开接口")
    posts = client.get("/api/posts").json()
    check("GET /api/posts", "items" in posts and "meta" in posts, str(posts)[:120])
    tags = client.get("/api/tags")
    check("GET /api/tags", tags.status_code == 200, tags.text)

    print("[3] 管理员登录 + CSRF")
    bad = client.post("/api/admin/login", json={"username": USERNAME, "password": "wrong"})
    check("错误密码返回 401", bad.status_code == 401, str(bad.status_code))
    login = client.post("/api/admin/login", json={"username": USERNAME, "password": PASSWORD})
    check("登录成功", login.status_code == 200, login.text)
    csrf = client.cookies.get("blog_admin_csrf")
    check("下发 CSRF cookie", bool(csrf))
    no_csrf = client.post("/api/admin/posts", json={"title": "x", "content_md": "y"})
    check("无 CSRF 被拒", no_csrf.status_code == 403, str(no_csrf.status_code))

    headers = {"X-CSRF-Token": csrf or ""}

    print("[4] 文章 CRUD")
    created = client.post(
        "/api/admin/posts",
        headers=headers,
        json={
            "title": "冒烟测试文章",
            "content_md": "# 标题\n\n正文 **加粗**\n\n```python\nprint('hi')\n```\n",
            "status": "draft",
            "tags": ["测试", "Python"],
        },
    )
    check("创建草稿", created.status_code == 201, created.text[:200])
    post = created.json()
    post_id, slug = post["id"], post["slug"]
    check("slug 为拼音", slug.startswith("mao-yan"), slug)
    check("自动摘要", bool(post["summary"]), post["summary"])
    check("Markdown 已渲染", "<strong>加粗" in post["content_html"])

    public = client.get(f"/api/posts/{slug}")
    check("草稿不出现在公开接口", public.status_code == 404, str(public.status_code))

    published = client.patch(
        f"/api/admin/posts/{post_id}", headers=headers, json={"status": "published"}
    )
    check("发布文章", published.status_code == 200 and published.json()["status"] == "published",
          published.text[:200])
    check("发布后写入 published_at", bool(published.json()["published_at"]))

    public = client.get(f"/api/posts/{slug}")
    check("发布后可公开访问", public.status_code == 200, public.text[:120])

    updated = client.patch(
        f"/api/admin/posts/{post_id}", headers=headers, json={"title": "冒烟测试文章（改）"}
    )
    check("修改标题", updated.status_code == 200 and "改" in updated.json()["title"])

    print("[5] 评论（蜜罐 / 限流 / 提交 / 审核）")
    honeypot = client.post(
        f"/api/posts/{slug}/comments",
        json={"author_name": "bot", "content": "ad", "captcha_id": "x",
              "captcha_answer": "y", "website": "http://spam"},
    )
    check("蜜罐拦截", honeypot.status_code == 400, honeypot.text)

    submitted = client.post(
        f"/api/posts/{slug}/comments",
        json={"author_name": "读者", "content": "写得好", "captcha_id": "ok", "captcha_answer": "ok"},
    )
    check("提交评论", submitted.status_code == 200, submitted.text)
    check("默认进待审", submitted.json().get("pending") is True, submitted.text)

    comments = client.get(f"/api/posts/{slug}/comments").json()
    check("待审评论不公开", comments == [], str(comments))

    pending = client.get("/api/admin/comments", params={"status": "pending"}).json()
    check("后台能看到待审", pending["meta"]["total"] >= 1, str(pending)[:150])
    comment_id = pending["items"][0]["id"]
    approved = client.post(f"/api/admin/comments/{comment_id}/approve", headers=headers)
    check("审核通过", approved.status_code == 200, approved.text)

    comments = client.get(f"/api/posts/{slug}/comments").json()
    check("通过后前台可见", len(comments) == 1, str(comments))

    print("[6] 图片上传")
    buffer = io.BytesIO()
    Image.new("RGB", (2400, 1200), (30, 120, 200)).save(buffer, format="PNG")
    upload = client.post(
        "/api/admin/media",
        headers=headers,
        files={"file": ("test.png", buffer.getvalue(), "image/png")},
    )
    check("上传成功", upload.status_code == 200, upload.text[:200])
    media = upload.json()
    check("转换并限制宽度", media["width"] == 1920, str(media))
    check("生成缩略图", media["thumb_url"].endswith("_thumb.webp"), media["thumb_url"])
    check("媒体可访问", client.get(media["url"]).status_code == 200)

    bad_upload = client.post(
        "/api/admin/media",
        headers=headers,
        files={"file": ("x.txt", b"not an image", "text/plain")},
    )
    check("非图片被拒", bad_upload.status_code == 400, bad_upload.text)

    print("[7] 清理")
    deleted = client.delete(f"/api/admin/posts/{post_id}", headers=headers)
    check("删除文章", deleted.status_code == 200, deleted.text)

    print()
    if failures:
        print(f"失败 {len(failures)} 项: {', '.join(failures)}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
