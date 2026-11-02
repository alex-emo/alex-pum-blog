"""图片上传处理：校验 → 限宽 → 转 WebP → 缩略图。"""
from __future__ import annotations

import io
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP"}
WEBP_QUALITY = 82


class UploadError(Exception):
    """上传失败，消息可直接展示给用户。"""


@dataclass
class SavedImage:
    url: str
    thumb_url: str
    width: int
    height: int
    bytes_written: int


def _target_dir() -> Path:
    now = datetime.now(timezone.utc)
    directory = settings.media_dir / now.strftime("%Y") / now.strftime("%m")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_image(raw: bytes, filename: str = "") -> SavedImage:
    if not raw:
        raise UploadError("文件为空")
    if len(raw) > settings.upload_max_bytes:
        limit_mb = settings.upload_max_bytes // (1024 * 1024)
        raise UploadError(f"图片超过 {limit_mb}MB 限制")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()  # 只验证完整性，verify 之后对象不可再用
    except (UnidentifiedImageError, OSError) as exc:
        raise UploadError("不是有效的图片文件") from exc

    # 重新打开，verify() 之后 image 对象已经不可用
    image = Image.open(io.BytesIO(raw))
    if image.format not in ALLOWED_FORMATS:
        raise UploadError(f"不支持的图片格式：{image.format}")

    # 手机拍的图常带 EXIF 旋转信息，先按 EXIF 摆正
    image = ImageOps.exif_transpose(image)

    # 统一转 RGBA/RGB，避免调色板或 CMYK 存 WebP 出错
    if image.mode in {"P", "LA", "RGBA"}:
        image = image.convert("RGBA")
    else:
        image = image.convert("RGB")

    max_width = settings.upload_image_max_width
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, int(image.height * ratio)), Image.LANCZOS)

    target_dir = _target_dir()
    stem = f"{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(6)}"
    main_path = target_dir / f"{stem}.webp"
    thumb_path = target_dir / f"{stem}_thumb.webp"

    image.save(main_path, format="WEBP", quality=WEBP_QUALITY, method=4)

    thumb_width = min(settings.upload_thumb_width, image.width)
    thumb_ratio = thumb_width / image.width
    thumb = image.resize((thumb_width, max(1, int(image.height * thumb_ratio))), Image.LANCZOS)
    thumb.save(thumb_path, format="WEBP", quality=WEBP_QUALITY, method=4)

    relative = main_path.relative_to(settings.media_dir).as_posix()
    thumb_relative = thumb_path.relative_to(settings.media_dir).as_posix()
    return SavedImage(
        url=f"{settings.media_url_prefix}/{relative}",
        thumb_url=f"{settings.media_url_prefix}/{thumb_relative}",
        width=image.width,
        height=image.height,
        bytes_written=main_path.stat().st_size,
    )


def delete_image(url: str) -> bool:
    """按 URL 删除媒体文件（防止 .. 穿越）。"""
    prefix = settings.media_url_prefix + "/"
    if not url.startswith(prefix):
        return False
    relative = url[len(prefix):]
    candidate = (settings.media_dir / relative).resolve()
    try:
        candidate.relative_to(settings.media_dir.resolve())
    except ValueError:
        return False
    if candidate.is_file():
        candidate.unlink()
        return True
    return False
