"""安全原语：密码哈希、会话签名、CSRF token。

- 密码：argon2id（内存硬，抗 GPU 爆破）
- 会话：itsdangerous 签名 token 放 httpOnly cookie，服务端无状态
- CSRF：双提交 cookie（cookie 与请求头里的 token 必须一致）
"""
from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

_password_hasher = PasswordHasher()

# 会话 token 的签名器；salt 隔离不同用途的 token
_session_serializer = URLSafeTimedSerializer(settings.secret_key, salt="admin-session")
_captcha_serializer = URLSafeTimedSerializer(settings.secret_key, salt="captcha")

CSRF_COOKIE_NAME = "blog_admin_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


# ---------------------------------------------------------------- 密码
def hash_password(raw: str) -> str:
    return _password_hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(hashed, raw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """argon2 参数升级后，登录成功时顺手重算一遍哈希。"""
    try:
        return _password_hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


# ---------------------------------------------------------------- 会话
def create_session_token(username: str) -> str:
    return _session_serializer.dumps({"u": username})


def read_session_token(token: str) -> str | None:
    """返回用户名；签名不对或过期返回 None。"""
    try:
        data = _session_serializer.loads(token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    username = data.get("u")
    return username if isinstance(username, str) else None


# ---------------------------------------------------------------- CSRF
def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
