# OPT-04 安全响应头：补 CSP 与 HSTS

| 项目 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 预计工时 | 2 h |
| 涉及文件 | `app/main.py`（`add_response_headers` 中间件）、`app/templates/base.html`、`app/templates/post.html`、Cloudflare 控制台 |
| 风险 | 中高（CSP 配错会白屏，务必先 Report-Only） |

## 问题

线上实测只有四个安全头：

```
x-content-type-options: nosniff
referrer-policy: strict-origin-when-cross-origin
x-frame-options: SAMEORIGIN
permissions-policy: camera=(), microphone=(), geolocation=()
```

**没有 CSP，也没有 HSTS。** 而站点正文来自 Markdown，`markdown_render.py` **没有做 HTML 白名单清洗**、模板以 `|safe` 输出——目前"只有管理员能写"所以风险自担，但一旦出现多作者、评论转 HTML、或导入外部 Markdown，就是存储型 XSS 直通车。CSP 是这条链路唯一的兜底。

另外 `deploy/DEPLOY.md:177` 写着"应该能看到 HSTS 头"，但当前链路（Cloudflare Tunnel → uvicorn，无 nginx）并没有设置，文档与事实不符。

## 方案

### 1. HSTS（5 min，最优先，收益/风险比最高）

在 Cloudflare 控制台 **SSL/TLS → Edge Certificates → HSTS** 开启：

- `max-age = 15552000`（180 天，初期可先用 86400 跑一天）
- 勾选 `Include SubDomains`（**确认 `pum.org.cn` 下没有仅 HTTP 的子域**再勾）
- 先**不要**开 Preload

程序侧不要在 uvicorn 里加 HSTS——HSTS 头必须在 HTTPS 响应上出现，而源站走的是 Tunnel 内部明文 HTTP。

### 2. CSP（分三步走）

**Step 1：Report-Only 观察一周**

```python
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self' https://cloudflareinsights.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)
response.headers.setdefault("Content-Security-Policy-Report-Only", CSP)
```

**Step 2：处理 `'unsafe-inline'`**

站点有两处内联脚本必须解决：

| 位置 | 内联内容 | 处理 |
| --- | --- | --- |
| `base.html` 首屏主题脚本 | 防闪白 | 用 `sha256-...` hash，或抽成 `theme-init.js` 内联 `<script>` 前先 `defer` 不可行（必须同步），推荐 **hash** |
| `base.html` / `post.html` JSON-LD | `<script type="application/ld+json">` | 用 hash |
| `profile_card.html` 移动端折叠 | 少量 JS | 抽成外部文件 |
| 各处 `style="..."`（如有） | 内联样式 | 用 `'unsafe-hashes'` 或改成类名 |

Jinja2 侧可以在 `app/templating.py` 暴露一个 `inline_hash` 过滤器，对内容做 `base64(sha256(content))`。

**Step 3：切换为强制执行**

把 `-Report-Only` 去掉，同时收紧：

```
script-src 'self' 'sha256-xxx' 'sha256-yyy';
style-src 'self' 'unsafe-inline';
```

> `style-src 'unsafe-inline'` 对纯静态 CSS 的站点风险很低（样式注入无法执行脚本），可以长期保留，换取内联 style 的灵活性。

### 3. 其他建议

- `X-Frame-Options: SAMEORIGIN` 与 CSP 的 `frame-ancestors 'none'` 语义**冲突**（前者允许同源嵌入，后者全部禁止）。站点没有 iframe 场景，建议统一成 `frame-ancestors 'none'` 并删掉 X-Frame-Options，或两者都改 `'self'`。
- 关闭 Cloudflare 的 **Email Address Obfuscation**（见 OPT-10），它会注入 `email-decode.min.js`，给 CSP 增加一个例外。
- 如需跨源隔离（暂不需要）：`Cross-Origin-Opener-Policy: same-origin`。

## 验收

- [ ] [securityheaders.com](https://securityheaders.com/?q=blog.pum.org.cn) 评级 ≥ **A**。
- [ ] `curl -I https://blog.pum.org.cn/ | grep -i strict-transport-security` 有输出，且 max-age ≥ 15768000。
- [ ] CSP 强制模式下：首页、文章页（含公式）、评论交互、后台登录、图片来源、MathJax 渲染全部正常，控制台 **0 条 CSP 报错**。
- [ ] `deploy/DEPLOY.md` 的验证章节同步更新为"在 Cloudflare 面板开启 HSTS"，不再误导。

## 回滚

CSP 出问题 → 把 `Content-Security-Policy` 改回 `Content-Security-Policy-Report-Only`，或删掉该行（中间件里一行注释即可）。
HSTS 出问题 → 先在 CF 面板把 max-age 调到 300，等浏览器过期；**切勿直接上 preload**。
