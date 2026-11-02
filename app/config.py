"""全局配置：全部从环境变量 / .env 读取，集中在一处方便部署。"""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（app/ 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent

# 先加载 .env，再读环境变量，这样 .env 里的值可以被真实环境变量覆盖
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Settings:
    """运行时配置。部署时通过 systemd EnvironmentFile 注入。"""

    def __init__(self) -> None:
        # ---- 站点信息 ----
        self.site_name: str = os.getenv("SITE_NAME", "Pum 的博客")
        self.site_description: str = os.getenv(
            "SITE_DESCRIPTION", "记录技术、折腾与日常。"
        )
        self.site_url: str = os.getenv("SITE_URL", "https://blog.pum.org.cn").rstrip("/")
        self.site_author: str = os.getenv("SITE_AUTHOR", "Pum")
        self.site_timezone: str = os.getenv("SITE_TIMEZONE", "Asia/Shanghai")

        # ---- 数据库 / 媒体 ----
        default_db = BASE_DIR / "blog.db"
        self.database_url: str = os.getenv(
            "DATABASE_URL", f"sqlite:///{default_db.as_posix()}"
        )
        self.media_dir: Path = Path(os.getenv("MEDIA_DIR") or (BASE_DIR / "media"))
        self.media_url_prefix: str = "/media"

        # ---- 安全 ----
        self.secret_key: str = os.getenv("SECRET_KEY") or ""
        if not self.secret_key:
            # 开发环境兜底：进程重启后所有登录态失效（生产必须显式配置）
            self.secret_key = secrets.token_hex(32)
            self.secret_key_is_temporary = True
        else:
            self.secret_key_is_temporary = False

        self.session_cookie: str = os.getenv("SESSION_COOKIE", "blog_admin_session")
        self.session_max_age: int = _int("SESSION_MAX_AGE", 14 * 24 * 3600)  # 14 天

        # ---- 站点行为 ----
        self.page_size: int = _int("PAGE_SIZE", 10)
        self.comment_require_approval: bool = _bool("COMMENT_REQUIRE_APPROVAL", True)
        self.comment_rate_seconds: int = _int("COMMENT_RATE_SECONDS", 30)
        self.comment_rate_per_hour: int = _int("COMMENT_RATE_PER_HOUR", 10)
        self.comment_attempts_per_hour: int = _int("COMMENT_ATTEMPTS_PER_HOUR", 40)
        self.upload_max_bytes: int = _int("UPLOAD_MAX_BYTES", 10 * 1024 * 1024)
        self.upload_image_max_width: int = _int("UPLOAD_IMAGE_MAX_WIDTH", 1920)
        self.upload_thumb_width: int = _int("UPLOAD_THUMB_WIDTH", 480)
        self.debug: bool = _bool("DEBUG", False)

        # HTTPS 部署时置 1，本地开发置 0（否则浏览器不发送 cookie）
        self.cookie_secure: bool = _bool("COOKIE_SECURE", False)

        self.app_dir: Path = BASE_DIR / "app"
        self.templates_dir: Path = self.app_dir / "templates"
        self.static_dir: Path = self.app_dir / "static"


settings = Settings()
