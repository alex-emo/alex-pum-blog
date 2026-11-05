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
    "pymdownx.tilde",      # ~~删除线~~
    "pymdownx.arithmatex", # 数学公式，输出 \( \) / \[ \] 交给 MathJax
]

_EXTENSION_CONFIGS = {
    "codehilite": {"css_class": "codehilite", "guess_lang": False, "linenums": False},
    "toc": {"permalink": False, "toc_depth": "2-4"},
    "pymdownx.arithmatex": {"generic": True, "smart_dollar": False},
}


def _normalize_math_blocks(text: str) -> str:
    """让独占一行的 $$ ... $$ 前后各空一行。

    Markdown 只有空行才分段，紧贴正文的 $$ 块会被并进同一个段落，
    arithmatex 就识别不到，只能原样输出。这里补上分段用的空行。
    """
    lines = (text or "").splitlines()
    out: list[str] = []
    i = 0
    in_fence = False
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        if not in_fence and stripped == "$$":
            j = i + 1
            while j < len(lines) and lines[j].strip() != "$$":
                j += 1
            if j < len(lines):
                if out and out[-1].strip():
                    out.append("")
                out.extend(lines[i : j + 1])
                if j + 1 < len(lines) and lines[j + 1].strip():
                    out.append("")
                i = j + 1
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _new_markdown() -> markdown.Markdown:
    return markdown.Markdown(extensions=_EXTENSIONS, extension_configs=_EXTENSION_CONFIGS)


_renderer = _new_markdown()


def render(text: str) -> str:
    """Markdown -> HTML 片段。"""
    _renderer.reset()
    return _renderer.convert(_normalize_math_blocks(text))


def render_with_toc(text: str) -> tuple[str, str]:
    """Markdown -> (HTML, 目录 HTML)。目录取 h2-h4，没有标题时返回空串。"""
    _renderer.reset()
    html = _renderer.convert(_normalize_math_blocks(text))
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


def has_math(html: str) -> bool:
    """正文是否包含数学公式（arithmatex 的产物），用于决定是否加载 MathJax。"""
    return 'class="arithmatex"' in (html or "")
