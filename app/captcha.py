"""自建图形验证码。

服务端生成 PNG，答案只存 sha256 摘要（内存，带 TTL 和一次性消费），
不依赖任何第三方服务，国内访问不受影响。
"""
from __future__ import annotations

import hashlib
import io
import random
import secrets
import threading
import time
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

CAPTCHA_TTL_SECONDS = 300      # 5 分钟有效
CAPTCHA_MAX_ENTRIES = 5000     # 防内存被刷爆
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # 去掉 l/1/i/0/o 这类易混字符


@dataclass
class _Entry:
    digest: str
    expires_at: float


class CaptchaStore:
    def __init__(self) -> None:
        self._items: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 内部
    def _cleanup(self, now: float) -> None:
        expired = [k for k, v in self._items.items() if v.expires_at < now]
        for key in expired:
            self._items.pop(key, None)
        # 还是太多就丢最早的（dict 保序）
        overflow = len(self._items) - CAPTCHA_MAX_ENTRIES
        if overflow > 0:
            for key in list(self._items)[:overflow]:
                self._items.pop(key, None)

    @staticmethod
    def _digest(answer: str) -> str:
        return hashlib.sha256(answer.strip().lower().encode()).hexdigest()

    # ------------------------------------------------------------ 对外
    def issue(self) -> tuple[str, bytes]:
        """生成一个新的验证码，返回 (captcha_id, PNG 字节)。"""
        answer = "".join(secrets.choice(_ALPHABET) for _ in range(4))
        png = _render_png(answer)

        captcha_id = secrets.token_urlsafe(16)
        now = time.time()
        with self._lock:
            self._cleanup(now)
            self._items[captcha_id] = _Entry(self._digest(answer), now + CAPTCHA_TTL_SECONDS)
        return captcha_id, png

    def verify(self, captcha_id: str | None, answer: str | None) -> bool:
        """校验并立即失效（一次性）。"""
        if not captcha_id or not answer:
            return False
        with self._lock:
            entry = self._items.pop(captcha_id, None)
        if entry is None or entry.expires_at < time.time():
            return False
        return secrets.compare_digest(entry.digest, self._digest(answer))


# ------------------------------------------------------------------ 绘制
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _render_png(answer: str, width: int = 132, height: int = 46) -> bytes:
    image = Image.new("RGB", (width, height), (250, 250, 248))
    draw = ImageDraw.Draw(image)

    # 干扰线
    for _ in range(6):
        draw.line(
            [(random.randint(0, width), random.randint(0, height)),
             (random.randint(0, width), random.randint(0, height))],
            fill=(random.randint(150, 210), random.randint(150, 210), random.randint(150, 210)),
            width=1,
        )
    # 噪点
    for _ in range(180):
        draw.point(
            (random.randint(0, width), random.randint(0, height)),
            fill=(random.randint(140, 220), random.randint(140, 220), random.randint(140, 220)),
        )

    font = _load_font(28)
    step = width // (len(answer) + 1)
    for index, char in enumerate(answer):
        tile = Image.new("RGBA", (44, 46), (0, 0, 0, 0))
        tile_draw = ImageDraw.Draw(tile)
        color = (random.randint(20, 90), random.randint(20, 90), random.randint(60, 140))
        tile_draw.text((6, 4), char, font=font, fill=color)
        tile = tile.rotate(random.uniform(-22, 22), expand=False, resample=Image.BICUBIC)
        image.paste(tile, (index * step + random.randint(0, 6), random.randint(-2, 3)), tile)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


captcha_store = CaptchaStore()
