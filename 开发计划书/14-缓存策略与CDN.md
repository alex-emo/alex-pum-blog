# OPT-14 缓存策略与 CDN

| 项目 | 内容 |
| --- | --- |
| 优先级 | P2 |
| 预计工时 | 3 h |
| 涉及文件 | `app/main.py`、`app/templating.py`（`asset_url`）、Cloudflare 控制台 / `deploy/` |
| 风险 | 中（缓存配错会显示旧内容） |

## 问题

| 资源 | 当前 | 问题 |
| --- | --- | --- |
| HTML | **无 `Cache-Control`、无 `ETag`** | 每次回源，CF `cf-cache-status: DYNAMIC`；连 304 条件请求都没有 |
| 静态 CSS/JS | `public, max-age=604800` + `?v=<mtime>` | 7 天太短，`?v=` 查询串在部分 CDN/代理上不参与缓存键 |
| 媒体 | `max-age=31536000, immutable` ✅ | 已经很好，不用动 |
| RSS | `max-age=600` ✅ | 合理 |
| 边缘 | 全部 `DYNAMIC` | 1 核机器独自扛所有请求 |

## 方案

### 1. 静态资源改内容哈希 + 一年 immutable

现在 `asset_url()` 用文件 mtime 做版本号，每次部署只要文件被 touch 就会撤销缓存——"安全"但低效。

改成**内容哈希**：

```python
# app/templating.py
def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]
```

启动时计算一次并缓存（静态文件不多，几毫秒）。URL 变成 `/static/css/style.css?v=a1b2c3d4e5`，配合：

```python
response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
```

> `immutable` 的语义是"在 max-age 内不发起任何校验请求"。内容变了 hash 就变，所以安全。

### 2. HTML 加条件请求

即使不上 CDN，至少让浏览器/CF 能走 304：

```python
# 在渲染后计算 ETag
etag = f'W/"{hashlib.md5(response.body).hexdigest()}"'
response.headers["ETag"] = etag
response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
if request.headers.get("if-none-match") == etag:
    return Response(status_code=304, headers={"ETag": etag})
```

### 3. 匿名 HTML 的边缘缓存（依赖 OPT-01）

完成 OPT-01 后（阅读量不再在 GET 里写库），文章页对"无登录态请求"可以安全缓存：

```
Cache-Control: public, max-age=300, stale-while-revalidate=600
```

Cloudflare 侧：

- **Caching → Cache Rules**：对 `/`、`/page/*`、`/tag/*`、`/{slug}`（排除 `/admin*`、`/api/*`）设 `Edge TTL = 10 min`；
- 保留 `bypass` 规则给后台与带 `Cookie: blog_admin_session` 的请求；
- 开启 **Tiered Cache** 与 **Early Hints**（可选）。

> 注意：CF Tunnel 下源站 IP 对内网，CF 缓存正常生效，只是当前 `Cache-Control` 不允许。

### 4. 资源提示

```html
<link rel="preload" href="{{ asset_url('/static/css/style.css') }}" as="style">
<link rel="preconnect" href="https://static.cloudflareinsights.com">  <!-- 若保留 RUM -->
```

首页 LCP 是文本（标题卡片），preload CSS 能缩短首绘；字体已是系统字体，无需 preload。

### 5. 部署后主动清理

内容哈希方案下**不需要**清理缓存；如果沿用 `?v=`，部署后在 CF 控制台 Purge Everything 一次（或用 API）。

## 验收

- [ ] `curl -sI https://blog.pum.org.cn/static/css/style.css | grep -i cache-control` → 含 `immutable`。
- [ ] 第二次访问 HTML，`curl -sI` 带 `If-None-Match` 返回 **304**。
- [ ] CF 控制台的缓存命中率（Analytics → Caching）从 ~0 提升到 > 50%（匿名请求为主）。
- [ ] 改一篇文章并发布，**10 分钟内**首页/文章页可见新内容（或在 CF 手动 purge 验证流程）。
- [ ] 登录后台后刷新前台文章页，**不出现他人登录态内容**（缓存键按 Cookie 区分或后台请求 bypass）。
- [ ] 部署新版本 CSS 后，浏览器立刻拿到新样式（hash 变化）。
