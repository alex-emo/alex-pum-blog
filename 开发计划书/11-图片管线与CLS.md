# OPT-11 图片管线与 CLS

| 项目 | 内容 |
| --- | --- |
| 优先级 | P1 |
| 预计工时 | 3 h |
| 涉及文件 | `app/media.py`、`app/static/css/style.css`（`.post-hero` / `.card-cover`）、`app/templates/post.html`、`app/templates/partials/macros.html` |
| 风险 | 中（涉及上传管线，老图需要兼容） |

## 问题

| # | 问题 | 证据 |
| --- | --- | --- |
| 1 | **封面图无 `srcset/sizes`** | `post-hero img` 只给 `src`，移动端下载桌面宽原图 |
| 2 | **无 `width/height`** | 靠 CSS `aspect-ratio` 兜底，比例对了，但首帧仍可能跳一下 |
| 3 | **只有一档缩略图** | `media.py` 出原图（≤1920 宽）+ `480` 缩略图，没有 960/1600 中间档 |
| 4 | **无 AVIF** | WebP 已经很好，但 AVIF 在照片类封面上再省 30–50% |
| 5 | **LCP 图无 `fetchpriority`** | 文章首屏封面是 LCP 候选，却没有 `fetchpriority="high"` |
| 6 | 卡片封面 `alt=""` | 正确（外层 a 已 `aria-hidden`，装饰图），**但**封面若承载信息则丢了描述 |
| 7 | 上传只按宽度限 1920 | 手机竖拍 1920×4000 的图，高度 4000，WebP 体积仍然很大；应同时限高 |

## 方案

### 1. 上传时出多档（`app/media.py`）

```python
WIDTHS = (480, 960, 1600)
# 原图仍保存（长边 1920），额外生成 WEBP_QUALITY 的三档
# 命名：<rand>.webp（原）、<rand>-480.webp、<rand>-960.webp、<rand>-1600.webp
```

`SavedImage` 增加 `widths: dict[int, str]`，写库时存成 JSON 或直接拼规则 URL（推荐后者：`/media/YYYY/MM/<rand>-{w}.webp`，无需改 schema）。

同时补一个**高度上限**（如 2560），防止异形图爆体积：

```python
max_h = settings.upload_image_max_height  # 默认 2560
if image.height > max_h:
    ...
```

### 2. 模板出 `srcset`

```jinja
{# post.html #}
{% if post.cover_image %}
<figure class="post-hero">
  <img src="{{ post.cover_image }}"
       srcset="{{ post.cover_image|media_set }}"
       sizes="(max-width: 800px) 100vw, 800px"
       width="{{ post.cover_width or 1600 }}"
       height="{{ post.cover_height or 640 }}"
       alt="{{ post.cover_alt or '' }}"
       fetchpriority="high"
       decoding="async">
</figure>
{% endif %}
```

`media_set` 过滤器负责拼 `xxx-480.webp 480w, xxx-960.webp 960w ...`，老图（没有多档）则退回单 `src`。

### 3. 卡片封面

`macros.html` 里：

```jinja
<img src="{{ post.thumb_image or post.cover_image }}"
     srcset="..."
     sizes="(max-width: 900px) 100vw, 640px"
     width="640" height="291"
     alt="" loading="lazy" decoding="async">
```

卡片在首屏下方，**保持 `loading="lazy"`**，不要加 `fetchpriority`。

> 注意：`aspect-ratio: 2.2/1` 与 `width="640" height="291"` 的比例（2.2:1）一致，避免被 CSS 强制裁剪时产生跳动。

### 4. `.post-hero` 的 aspect-ratio 统一

```css
.post-hero img { width: 100%; aspect-ratio: 2.6 / 1; object-fit: cover; border-radius: var(--radius); }
@media (max-width: 480px) { .post-hero img { aspect-ratio: 16 / 9; } }
```

比例在断点处变化（2.6 → 1.78）会导致**断点处的 CLS**。建议全站统一用 `2.2 / 1`（与卡片一致），或统一 `16/9`，避免响应式切换。

### 5. AVIF（可选）

```python
# 若 Pillow 支持（>= 9.1 且编译了 libavif）
image.save(path.with_suffix('.avif'), format='AVIF', quality=60)
```

模板用 `<picture><source type="image/avif" ...><source type="image/webp" ...><img ...></picture>`。
收益：照片类封面体积再降 30–50%；成本：编码时间 / 服务器 CPU（1 核会明显变慢，建议**只在管理员上传时同步转**，因为上传频率低）。

## 验收

- [ ] 375 px 视口下，文章页封面下载的图片宽度 ≤ 960（DevTools Network 里看）。
- [ ] Lighthouse CLS = 0（首页 + 文章页）。
- [ ] 老图（只有原图）不报 404，`<picture>` 回退正常。
- [ ] 上传 1920×4000 的竖图，出片高度 ≤ 2560。
- [ ] LCP 元素是封面图时，Network 面板里该请求有 `High` 优先级。

## 实测结果

| 项目 | 优化前 | 优化后 |
| --- | --- | --- |
| 文章页封面下载宽度（375 px 视口） | 原图（≤1920） | 待填 |
| CLS（文章页） | 待测 | 待填 |
