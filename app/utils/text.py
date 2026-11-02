"""通用工具：文本处理（slug / 摘要 / 阅读时长）。"""
from __future__ import annotations

import re
import unicodedata

from pypinyin import Style, lazy_pinyin

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_MD_SYNTAX = re.compile(
    r"```.*?```|~~~.*?~~~"      # 代码块
    r"|`[^`]*`"                # 行内代码
    r"|!\[[^\]]*\]\([^)]*\)"   # 图片
    r"|\[([^\]]*)\]\([^)]*\)"  # 链接 -> 保留文字
    r"|^#{1,6}\s*"             # 标题符号
    r"|<[^>]+>",               # HTML 标签
    re.S | re.M,
)


def slugify(text: str) -> str:
    """生成 URL slug。

    纯英文直接 lowercase + 连字符；中文标题转拼音
    （"我的第一篇" -> "wo-de-di-yi-pian"），这样 URL 可读可复制，
    也不会出现一长串百分号编码。
    """
    text = (text or "").strip()
    if not text:
        return ""

    if text.isascii():
        return _SLUG_STRIP.sub("-", text.lower()).strip("-")

    # lazy_pinyin 对中英混排友好：中文转拼音，非中文段落原样保留
    merged = "-".join(lazy_pinyin(text, style=Style.NORMAL))
    merged = unicodedata.normalize("NFKD", merged)
    # 去掉声调符号这类组合字符
    merged = "".join(c for c in merged if not unicodedata.combining(c))
    return _SLUG_STRIP.sub("-", merged.lower()).strip("-")


def unique_slug(base: str, exists: "callable[[str], bool]", fallback: str = "post") -> str:
    """保证 slug 唯一：重名时追加 -2, -3 …"""
    base = base or fallback
    if not exists(base):
        return base
    for i in range(2, 1000):
        candidate = f"{base}-{i}"
        if not exists(candidate):
            return candidate
    return f"{base}-{abs(hash(base)) % 100000}"


def excerpt(text: str, limit: int = 160) -> str:
    """从 Markdown 正文里粗略抽取纯文本摘要。"""
    plain = _MD_SYNTAX.sub(lambda m: m.group(1) or "", text or "")
    # 清掉引用、列表符号和强调标记
    plain = re.sub(r"^\s{0,3}(?:>\s?|[-*+]\s|\d+\.\s)", "", plain, flags=re.M)
    plain = re.sub(r"[*_~`]+", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) <= limit:
        return plain
    return plain[:limit].rstrip() + "…"


def reading_minutes(text: str) -> int:
    """按 400 字/分钟估算阅读时长，至少 1 分钟。"""
    chars = len(re.sub(r"\s+", "", text or ""))
    return max(1, round(chars / 400))
