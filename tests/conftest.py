"""pytest 环境：每个测试会话用独立的临时数据库和媒体目录，绝不碰 blog.db。

注意：这些环境变量必须在 import app 之前设置，config 在导入时读取。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="blog-pytest-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(_TMP / 'test.db').as_posix()}")
os.environ.setdefault("MEDIA_DIR", str(_TMP / "media"))
os.environ.setdefault("SECRET_KEY", "pytest-only-secret")
os.environ.setdefault("COOKIE_SECURE", "0")
os.environ.setdefault("DEBUG", "0")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("COMMENT_REQUIRE_APPROVAL", "1")
os.environ.setdefault("SITE_URL", "http://testserver")

from fastapi.testclient import TestClient  # noqa: E402

from app.captcha import captcha_store  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import rate_limiter  # noqa: E402


@pytest.fixture
def client():
    # 必须用 with：Starlette 只有进入上下文才会执行 lifespan（迁移 + 建管理员）
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """每个测试都从干净的限流状态开始，避免 10 次登录限制串扰。"""
    rate_limiter.clear()
    yield


@pytest.fixture(autouse=True)
def skip_captcha(monkeypatch):
    """验证码本身在 test_captcha 里单独测，其余测试绕过。"""
    monkeypatch.setattr(captcha_store, "verify", lambda captcha_id, answer: True)


@pytest.fixture
def login(client):
    """登录并返回带 CSRF 头的字典。"""
    response = client.post(
        "/api/admin/login", json={"username": "admin", "password": "test-password"}
    )
    assert response.status_code == 200, response.text
    csrf = client.cookies.get("blog_admin_csrf")
    assert csrf
    return {"X-CSRF-Token": csrf}


@pytest.fixture
def published_post(client, login):
    response = client.post(
        "/api/admin/posts",
        headers=login,
        json={
            "title": "测试用文章",
            "content_md": "## 小节\n\n正文。",
            "status": "published",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
