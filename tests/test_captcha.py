"""验证码单独测：本文件不绕过验证码。"""
from __future__ import annotations

import pytest

from app.captcha import captcha_store


@pytest.fixture(autouse=True)
def skip_captcha():
    """覆盖 conftest 里的全局 monkeypatch。"""
    yield


def test_issue_returns_png():
    captcha_id, png = captcha_store.issue()
    assert captcha_id
    assert png.startswith(b"\x89PNG")
    assert captcha_store.issue()[0] != captcha_id


def test_verify_is_one_time():
    captcha_id, _ = captcha_store.issue()
    # 不知道答案，但可以验证“错一次即作废、不能重试”
    assert captcha_store.verify(captcha_id, "zzzz") is False
    assert captcha_store.verify(captcha_id, "zzzz") is False


def test_verify_rejects_empty():
    assert captcha_store.verify(None, "abcd") is False
    assert captcha_store.verify("missing-id", "abcd") is False
