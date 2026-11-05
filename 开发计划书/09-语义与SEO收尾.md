# OPT-09 语义与 SEO 收尾

| 项目 | 内容 |
| --- | --- |
| 优先级 | P1 |
| 预计工时 | 2 h |
| 涉及文件 | `app/templates/index.html`、`app/templates/search.html`、`app/templates/base.html`、`app/routers/pages.py`、`app/routers/feeds.py` |
| 风险 | 低 |

## 问题清单

| # | 问题 | 证据 |
| --- | --- | --- |
| 1 | **首页没有 h1** | `index.html` 只有 `{% if heading %}` 才输出 h1；线上首页 `h1Count = 0`，标题直接从 H2 开始 |
| 2 | **搜索页被索引且 canonical 丢 query** | `/search?q=st` 返回 200 且无 `noindex`；canonical 取 `request.url.path` → `https://blog.pum.org.cn/search`（指向空搜索页） |
| 3 | 分页页的 canonical 指向第 1 页 | `/page/2` 的 canonical 是 `/page/2`？——实际取 `url.path` 所以是对的，但**第 1 页与首页重复**，需要 canonical 互指 |
| 4 | `og:url` 同样丢 query | `base.html` 用 `request.url.path` |
| 5 | sitemap 缺 `lastmod` | 首页、`/tags`、tag 页都没有；搜索引擎无法判断新鲜度 |
| 6 | 分页页无限软 404（见 OPT-05） | `/page/999` → 200 |
| 7 | 无 `<meta name="robots">` | 全站依赖默认 |
| 8 | 标签页 title/description 重复度 | `标签：算法` 这类页面 description 沿用 `SITE_DESCRIPTION` |
| 9 | `theme-color` 与 CSS 不一致 | 见 OPT-08 |
| 10 | 无 `hreflang`（单语言，可忽略） | — |

## 方案

### 1. 首页 h1

```jinja
{# index.html #}
{% if heading %}
  <h1 class="page-heading">{{ heading }}</h1>
{% else %}
  <h1 class="page-heading sr-only">最新文章</h1>
{% endif %}
```

`.sr-only` 已有（`base.html` 里搜索框 label 在用），视觉上不出现但读屏与搜索引擎可见。若想视觉上也出现，可以把侧栏的站名/签名提升为 h1 并给卡片标题降级——**不推荐**，改动大且卡片 h2 的语义是对的。

### 2. noindex 策略

| 页面 | robots |
| --- | --- |
| `/search*` | `noindex, follow`（有查询参数时尤其必要） |
| `/page/N`（N ≥ 2） | 不 noindex，但 canonical 指向自身 |
| `/tag/*` | 允许索引（有内容），但内容不足的标签页可 `noindex, follow` |
| `/admin*` | 已有 `X-Robots-Tag`，再加 `<meta>` 双保险 |

在 `base.html` 加块：

```jinja
{% block robots %}<meta name="robots" content="index, follow">{% endblock %}
```

`search.html` 里覆盖为 `noindex, follow`。

### 3. canonical 修正

`base.html` 目前：

```jinja
<link rel="canonical" href="{% block canonical %}{{ settings.site_url }}{{ request.url.path }}{% endblock %}">
```

搜索页覆盖：

```jinja
{% block canonical %}{{ settings.site_url }}{% endblock %}
```

（搜索页既然 noindex，canonical 指向首页反而制造"重复内容"信号，最稳妥是**不输出 canonical**，或指向首页并配合 noindex。）推荐：

```jinja
{# search.html #}
{% block head %}
  {{ super() }}
  {# 不输出 canonical，只 noindex #}
{% endblock %}
```

同时 `og:url` 对文章页保持现状（文章页无 query），对搜索页无意义（已 noindex）。

### 4. sitemap 补 lastmod

`app/routers/feeds.py` 里首页与标签页目前没有 `<lastmod>`。改成"最近一篇文章的 `updated_at`"即可：

```python
latest = _published_posts(db, limit=1)
lastmod = to_local(latest[0].updated_at or latest[0].created_at).strftime("%Y-%m-%d") if latest else None
```

或者对首页干脆不加——Google 已忽略 sitemap 的 `priority` / `changefreq`，`lastmod` 只在准确时有用。**有确切时间才加，不要伪造。** 这条是"可选优化"，不做也不算错。

### 5. 标签页的 title / description

```jinja
{# index.html #}
{% block title %}{% if heading %}{{ heading }} · {{ settings.site_name }}{% else %}{{ settings.site_name }}{% endif %}{% endblock %}
{% block description %}{% if heading %}{{ heading }} —— {{ settings.site_description }}{% else %}{{ settings.site_description }}{% endif %}{% endblock %}
```

### 6. 结构化数据补充

- 首页可加 `Blog` 类型 + `ItemList`（文章列表）；
- 文章页已有 `BlogPosting`，建议补 `wordCount`、`timeRequired`（`PT{{ minutes }}M`）、`image`（无封面时用默认 OG 图，配合 OPT-03）。

## 验收

- [ ] `curl -s https://blog.pum.org.cn/ | grep -c '<h1'` → 1。
- [ ] `curl -s 'https://blog.pum.org.cn/search?q=st' | grep -o 'name="robots"[^>]*'` → `noindex`。
- [ ] 用 [Rich Results Test](https://search.google.com/test/rich-results) 测首页与文章页无错误。
- [ ] Google Search Console "覆盖率"里不再出现 `/search?q=*` 的软 404。
- [ ] Lighthouse SEO ≥ 100。
- [ ] `/page/2` 与 `/` 的 canonical 关系正确（各自指向自身，或第 2 页也指向 `/` 并确认内容差异足够）。
