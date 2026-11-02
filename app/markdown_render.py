"""Markdown 渲染。文章发布时渲染一次存库，读接口直接用 HTML，省 CPU。"""
from __future__ import annotations

import markdown
from pygments.formatters import HtmlFormatter

_EXTENSIONS = [
    "fenced_code",   # ``` 代码块
    "codehilite",    # 代码高亮（Pygments）
    "tables",        # 表格
    "toc",           # 标题锚点 + 目录
    "sane_lists",    # 列表解析更符合直觉
    "nl2br",         # 单个换行即换行，中文写作习惯
    "attr_list",     # 允许 {: .cls } 之类的属性
]

_EXTENSION_CONFIGS = {
    "codehilite": {"css_class": "codehilite", "guess_lang": False, "linenums": False},
    "toc": {"permalink": False, "toc_depth": "2-4"},
}


def _new_markdown() -> markdown.Markdown:
    return markdown.Markdown(extensions=_EXTENSIONS, extension_configs=_EXTENSION_CONFIGS)


_renderer = _new_markdown()


def render(text: str) -> str:
    """Markdown -> HTML 片段。"""
    _renderer.reset()
    return _renderer.convert(text or "")


def render_with_toc(text: str) -> tuple[str, str]:
    """Markdown -> (HTML, 目录 HTML)。目录取 h2-h4，没有标题时返回空串。"""
    _renderer.reset()
    html = _renderer.convert(text or "")
    toc = getattr(_renderer, "toc", "") or ""
    if "<li>" not in toc:
        toc = ""
    return html, toc


def pygments_css(light_style: str = "friendly", dark_style: str = "one-dark") -> str:
    """生成代码高亮 CSS：浅色为默认，深色挂在 html[data-theme="dark"] 下。

    主题由前端三态开关控制（data-theme），所以不能再用 prefers-color-scheme。
    """
    light = HtmlFormatter(style=light_style).get_style_defs(".codehilite")
    dark = HtmlFormatter(style=dark_style).get_style_defs(".codehilite")
    dark_block = "\n".join("  " + line if line.strip() else line for line in dark.splitlines())
    return (
        "/* 浅色主题 */\n" + light + "\n\n"
        'html[data-theme="dark"] {\n  /* 深色主题 */\n' + dark_block + "\n}\n"
    )
