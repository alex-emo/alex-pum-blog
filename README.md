# Pum 的博客

个人博客：Jinja2 服务端渲染 + FastAPI 后台 + SQLite。为 2 核 1G 的小机器设计，不跑 Node、不跑 Redis。

## 功能

**前台**：文章列表分页、标签、搜索、Markdown 详情（代码高亮 + 目录）、上下篇、RSS、sitemap、robots、深浅色自适应、移动端适配。

**后台**（`/admin`）：密码登录、仪表盘、文章增删改（实时预览、粘贴/拖拽上传图片、Ctrl+S 保存）、评论审核（通过/拒绝/删除）。

**评论**：匿名可评，自建图片验证码 + 蜜罐字段 + IP 限流（30 秒 1 条 / 每小时 10 条）+ 默认进待审。

**图片**：上传后 Pillow 校验、按 EXIF 摆正、限宽 1920、转 WebP 并生成 480 宽缩略图，存 `media/YYYY/MM/`，生产环境由 nginx 直接托管。

## 目录

```
app/
├── main.py             应用组装（挂载、路由顺序、异常页）
├── config.py           全部配置来自环境变量 / .env
├── database.py         SQLite + WAL，get_db 依赖
├── models.py           Post / Tag / Comment / AdminUser
├── schemas.py          Pydantic 入出参
├── security.py         argon2 密码 + itsdangerous 会话 cookie + CSRF
├── captcha.py          自建验证码（Pillow）
├── ratelimit.py        内存滑动窗口限流
├── media.py            图片处理与存储
├── markdown_render.py  Markdown 渲染（内容存 HTML，读取不再渲染）
├── templating.py       Jinja2 环境、过滤器、分页
├── services/           文章、评论业务逻辑
├── routers/            public_* 公开接口 / admin_* 后台接口 / pages 页面 / feeds
├── migrations/         轻量迁移（schema_version + mNNNN_*.py）
├── templates/          Jinja2 模板（含 admin/）
└── static/             CSS / JS / favicon
scripts/
├── manage.py           migrate、create-admin、reset-password、export-css
├── backup.py           数据库 + 媒体备份
└── smoke_test.py       30 项冒烟测试
deploy/                 nginx、systemd、备份 timer、部署文档
```

## 本地运行

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env            # 按需修改，SECRET_KEY 生产必须换
venv/bin/python -m scripts.manage migrate
venv/bin/python -m scripts.manage create-admin admin --password '你的密码'
venv/bin/uvicorn app.main:app --port 8010 --reload
```

打开 <http://127.0.0.1:8010>，后台在 `/admin`。

测试（都在临时库上跑，不碰 `blog.db`）：

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest            # 11 项关键链路测试，约 2 秒
venv/bin/python -m scripts.smoke_test # 30 项浏览器/接口冒烟
```

## 常用操作

```bash
# 改密码
venv/bin/python -m scripts.manage reset-password admin

# 生成代码高亮 CSS（改了主题才需要）
venv/bin/python -m scripts.manage export-css app/static/css/pygments.css

# 手动备份（默认保留 14 天）
venv/bin/python -m scripts.backup --keep 14
```

## 部署

见 [deploy/DEPLOY.md](deploy/DEPLOY.md)：Debian 12 + nginx + systemd + certbot，单 uvicorn worker，SQLite 开 WAL。

关键环境变量：

| 变量 | 说明 |
| --- | --- |
| `SECRET_KEY` | 会话签名密钥，生产必填，泄露等于后台失守 |
| `COOKIE_SECURE` | HTTPS 部署置 1 |
| `DEBUG` | 生产置 0，关闭 `/api/docs` |
| `SITE_URL` | 用于 RSS / sitemap / 分享卡片绝对地址 |
| `SITE_SIGNATURE` | 侧栏一句话签名 |
| `SITE_AVATAR` | 侧栏头像地址，默认 `/static/img/avatar.png` |
| `SITE_EMAIL` / `SITE_X` / `SITE_TELEGRAM` | 侧栏联系方式（邮箱 / X 用户名 / Telegram 用户名） |
| `COMMENT_REQUIRE_APPROVAL` | 1=先进待审；0=直接显示（本项目本地用 0） |
