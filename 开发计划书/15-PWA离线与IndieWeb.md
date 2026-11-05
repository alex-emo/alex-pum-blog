# OPT-15 PWA 离线与 IndieWeb

| 项目 | 内容 |
| --- | --- |
| 优先级 | P2 |
| 预计工时 | 6 h |
| 涉及文件 | `app/static/site.webmanifest`、新增 `app/static/sw.js`、`app/templates/base.html`、`app/templates/partials/profile_card.html`、新增 `/webmention` 回调 |
| 风险 | 中（SW 更新策略配错会导致"改不动"） |

## 问题

- **已有 `site.webmanifest`，但没有 Service Worker**，所以不是"可安装的 PWA"，也没有离线能力；
- 没有 `rel="me"`、没有 microformats2、没有 Webmention 接收，与"个人博客接回开放网络"的趋势脱节（你自己的文章 `text/blogvuild.md` 里也提到"联邦宇宙"）。

## 方案

### 1. Service Worker 离线壳（半天）

分两层：

```js
// app/static/sw.js
const CORE = '/sw-shell-v1';
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CORE).then(c => c.addAll(['/offline'])));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== CORE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', e => {
  if (e.request.mode === 'navigate') {
    e.respondWith(fetch(e.request).catch(() => caches.match('/offline')));
  }
});
```

注册放在 `theme.js` 或新文件里（`navigator.serviceWorker.register('/sw.js')`）。

**策略要点**：

- **HTML 网络优先**，离线时回退 `/offline` 静态页——避免用户看到几天前的首页；
- **静态资源缓存优先**（文件名带 hash，见 OPT-14）；
- **后台、API 一律不缓存**；
- 改动 SW 时记得升版本号并清理旧 cache。

### 2. 离线页

`GET /offline`，一个静态 HTML（或复用 error 模板），告诉用户"当前离线，已缓存内容可能不是最新"。

### 3. manifest 补全

```json
{
  "name": "Alex 的博客",
  "short_name": "Alex",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#f6f8fb",
  "theme_color": "#f6f8fb",
  "icons": [
    { "src": "/static/img/icon-192.webp", "sizes": "192x192", "type": "image/webp" },
    { "src": "/static/img/icon-512.webp", "sizes": "512x512", "type": "image/webp" },
    { "src": "/static/img/icon-maskable-512.webp", "sizes": "512x512", "type": "image/webp", "purpose": "maskable" }
  ]
}
```

（当前 manifest 的图标是 PNG，见 OPT-06。）

### 4. IndieWeb 第一步：`rel="me"`（10 分钟）

页脚或「关于」页：

```html
<a rel="me" href="https://x.com/ParameciumAlex">X</a>
<a rel="me" href="https://t.me/praeity">Telegram</a>
<a rel="me" href="mailto:alex12141327@163.com">邮箱</a>
```

配合已存在的社交链接，你的 Mastodon / 其它支持 `rel=me` 的平台可验证域名归属。

### 5. microformats2 `h-entry`（半天）

文章页的 `<article>` 加类名：

```html
<article class="post h-entry">
  <h1 class="p-name">{{ post.title }}</h1>
  <time class="dt-published" datetime="...">...</time>
  <div class="e-content">{{ post.content_html|safe }}</div>
  <a class="p-author h-card" rel="author" href="/">{{ settings.site_author }}</a>
</article>
```

这样 IndieWeb 生态（webmention.io、Bridgy、微格式解析器）能自动识别你的文章。

### 6. Webmention 接收（1 天，可选）

1. 在 [webmention.io](https://webmention.io/) 注册，拿到 endpoint；
2. `<link rel="webmention" href="https://webmention.io/blog.pum.org.cn/webmention">`；
3. 把收到的 webmention 作为**特殊评论**渲染（`Comment.source = 'webmention'`），走现有审核流程；
4. 发送端可接 Bridgy 把 X / Mastodon 的提及回传。

### 7. 联邦宇宙（暂不做）

ActivityPub 需要长期维护 actor、inbox/outbox、签名校验，对单管理员的静态博客不划算。**等有稳定读者再说**。

## 验收

- [ ] Chrome DevTools → Application → Service Workers 显示已注册、无报错。
- [ ] Lighthouse PWA 检查通过（可安装）。
- [ ] 断网后刷新任意页面，返回离线页而不是浏览器恐龙。
- [ ] 改一篇文章发布后，普通刷新能立即看到新内容（SW 网络优先策略生效）。
- [ ] [IndieWebify.me](https://indiewebify.me/) 的 "Validate your h-entry" 通过。
- [ ] `rel=me` 在 [Mastodon](https://mastodon.social/) 个人资料页验证域名成功。
