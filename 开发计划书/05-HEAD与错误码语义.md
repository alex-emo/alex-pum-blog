# OPT-05 HEAD 支持与错误码语义

| 项目 | 内容 |
| --- | --- |
| 优先级 | P0 |
| 预计工时 | 1 h |
| 涉及文件 | `app/main.py`、`app/routers/pages.py`、`app/templating.py` |
| 风险 | 低 |

## 问题

线上实测：

| 请求 | 当前结果 | 期望 |
| --- | --- | --- |
| `HEAD /` | **405** | 200 |
| `GET /page/999` | **200** + "这里还没有文章" | 404 |
| `GET /page/0` | 200 | 404（或 301 到第 1 页） |
| `GET /page/abc` | **422 纯文本** | 404 错误页（人类可读） |
| `GET /tag/nope` | 404 ✅ | — |
| `GET /nope` | 404 ✅ | — |

三个实际影响：

1. **HEAD 405 会打断监控**。Uptime 探针、链接检查器、部分 CDN 预取、`curl -I` 都走 HEAD，现在全部拿到 405。
2. **无限软 404**。`/page/999`、`/page/10000`…… 每个都能返回 200，爬虫可以无限抓下去，属于典型的 SEO 陷阱。
3. **422 是纯文本**。`HTTPException` 里除 404/5xx 外都返回 `Response(content=str(exc.detail), media_type="text/plain")`，用户看到的是一个裸字符串而不是站点页。

## 方案

### 1. HEAD

FastAPI / Starlette 默认不会给 `@router.get` 自动注册 HEAD。在 `app/main.py` 里加一个兜底中间件最省事：

```python
@app.middleware("http")
async def allow_head(request: Request, call_next):
    if request.method == "HEAD":
        request.scope["method"] = "GET"
    response = await call_next(request)
    # 保持语义：HEAD 响应不带 body（ASGI 会自己处理，这里只是确保）
    return response
```

或者更干净地在 `pages.feeds.router` 里为每个路由补 `methods=["GET", "HEAD"]`（模板渲染开销仍在，但语义正确）。

> 注意：HEAD 若走了 OPT-01 之前的写库路径，也会插一次阅读量——所以 **OPT-01 应先做**。

### 2. 分页越界

`_list_page` 里目前没判越界。加：

```python
if result.total and page > result.total_pages:
    return pages.not_found(request)
if page < 1:
    return pages.not_found(request)
```

`/page/0` 也可以改成 301 到 `/`，但对博客来说 404 更简单。

顺带修 `/tag/{slug}/page/{n}`、`/search/page/{n}` 的同一逻辑。

### 3. 参数异常走错误页

`RequestValidationError` 是 FastAPI 的独立异常类，不走 `HTTPException` 处理器。可以：

- 加 `@app.exception_handler(RequestValidationError)`，页面请求返回 `error.html`（status 404 或 422），API 请求仍返回 JSON；
- 或者把 `/page/{page}` 的 `page: int` 改成 `page: str`，自己 `int()` 转换，失败就 404。

推荐前者，一处改动覆盖全部路由。

### 4. 顺手补的其他状态码

- `OPTIONS /` 应返回 204 或带 `Allow` 头（现有 CORS 未配，GET 默认应支持）。
- 若将来开 API，`405` 响应应带 `Allow` 头（FastAPI 默认会带）。

## 验收

```bash
curl -sI https://blog.pum.org.cn/ | head -1          # HTTP/2 200
curl -sI https://blog.pum.org.cn/rss.xml | head -1   # 200
curl -s -o /dev/null -w '%{http_code}\n' https://blog.pum.org.cn/page/999   # 404
curl -s -o /dev/null -w '%{http_code}\n' https://blog.pum.org.cn/page/abc   # 404 或 422，但是 HTML 页
curl -s https://blog.pum.org.cn/page/999 | grep -c '这里还没有文章'          # 0
```

- [ ] 上述全部通过。
- [ ] sitemap 里不含 `/page/N` 的越界 URL（现在本来也不含，确认不要加）。
- [ ] `scripts/smoke_test.py` 补充 HEAD 与越界分页的用例。
