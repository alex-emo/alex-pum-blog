# 部署到 blog.pum.org.cn

目标环境：阿里云 Debian 12（2 核 1G），nginx + systemd + uvicorn 单进程 + SQLite。

```
浏览器 → nginx :443 → uvicorn 127.0.0.1:8010 → app/
                     ├── /static/  nginx 直接读 app/static/
                     └── /media/   nginx 直接读 media/
```

## 0. 首次准备服务器

```bash
# root 登录后
apt update && apt install -y python3 python3-venv python3-pip nginx sqlite3 rsync ufw

# 1G 内存务必加 swap，否则 pip 编译/临时峰值会 OOM
fallocate -l 2G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 建运行用户（不能登录 shell）
useradd --system --home /srv/blog --shell /usr/sbin/nologin blog
mkdir -p /srv/blog && chown -R blog:blog /srv/blog

# 关键：服务以 UMask=0027 运行，media 文件是 640 blog:blog，
# nginx（www-data）要读图片必须进 blog 组，否则 /media/ 全 403
usermod -aG blog www-data
systemctl restart nginx

# 防火墙
ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw --force enable
```

## 1. 上传代码

在本地项目目录：

```bash
rsync -avz --delete \
  --exclude venv --exclude __pycache__ --exclude '*.pyc' \
  --exclude .env --exclude blog.db --exclude 'blog.db-*' \
  --exclude media --exclude backups --exclude .git \
  ./ root@blog.pum.org.cn:/srv/blog/
```

## 2. 安装依赖

```bash
cd /srv/blog
sudo -u blog python3 -m venv venv
sudo -u blog venv/bin/pip install --upgrade pip
sudo -u blog venv/bin/pip install -r requirements.txt
```

## 3. 配置 .env

```bash
cd /srv/blog
cp .env.example .env
# 生成随机 SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"
chmod 600 .env && chown blog:blog .env
```

编辑 `/srv/blog/.env`，至少确认：

```ini
SITE_URL=https://blog.pum.org.cn
SECRET_KEY=<上一步生成的 64 位十六进制>
COOKIE_SECURE=1
DEBUG=0
ADMIN_USERNAME=pum            # 首次启动自动建号；建好后可以删掉这两行
ADMIN_PASSWORD=<一个强密码>
COMMENT_REQUIRE_APPROVAL=1
```

> `COOKIE_SECURE=1` 只在 HTTPS 下生效；本地开发保持 0，否则登录 cookie 不会被浏览器保存。

## 4. 初始化数据库

```bash
cd /srv/blog
sudo -u blog venv/bin/python -m scripts.manage migrate
# 直接指定密码建号（不走 env 自动建号也可以）
sudo -u blog venv/bin/python -m scripts.manage create-admin pum --password '你的密码'
```

## 5. systemd 服务

```bash
cp /srv/blog/deploy/blog.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now blog
systemctl status blog --no-pager
curl -s http://127.0.0.1:8010/api/health
```

日志：`journalctl -u blog -f`
重启：`systemctl restart blog`

## 6. nginx + HTTPS

```bash
cp /srv/blog/deploy/nginx-blog.conf /etc/nginx/sites-available/blog
ln -s /etc/nginx/sites-available/blog /etc/nginx/sites-enabled/blog
rm -f /etc/nginx/sites-enabled/default
```

配置里 443 段的证书路径还不存在，所以先用一张 1 天的自签证书占位，让 `nginx -t` 通过；
再用 webroot 方式签发真证书覆盖同名文件（不动 nginx 配置，避免 certbot 改写我们手写的段）：

```bash
apt install -y certbot
mkdir -p /etc/letsencrypt/live/blog.pum.org.cn
openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -subj "/CN=blog.pum.org.cn" \
  -keyout /etc/letsencrypt/live/blog.pum.org.cn/privkey.pem \
  -out /etc/letsencrypt/live/blog.pum.org.cn/fullchain.pem
nginx -t && systemctl reload nginx

# 真证书（80 端口的 ACME 路径已在配置里放行）
certbot certonly --webroot -w /var/www/html -d blog.pum.org.cn \
  -m 你的邮箱 --agree-tos --no-eff-email
nginx -t && systemctl reload nginx
```

> 如果 DNS 还没解析到这台机器，certbot 会失败：先把 `blog.pum.org.cn` 的 A 记录指过来，再执行。

验证：`curl -I https://blog.pum.org.cn` 应为 200，并且有 HSTS 头。

续期由 `certbot.timer` 自动完成，但 webroot 方式不会自动 reload nginx，加一个部署钩子：

```bash
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
systemctl list-timers certbot.timer
certbot renew --dry-run
```

## 7. 每日备份

```bash
cp /srv/blog/deploy/blog-backup.service /srv/blog/deploy/blog-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now blog-backup.timer
systemctl list-timers blog-backup.timer
# 立刻手动跑一次
sudo -u blog /srv/blog/venv/bin/python -m scripts.backup --keep 14
```

备份在 `/srv/blog/backups/`：`blog-*.db`（SQLite 在线快照，WAL 一致）+ `media-*.tar.gz`，保留 14 天。
建议再定期把备份目录 `rsync` 到本地或对象存储（异地备份才算备份）。

## 8. 日常更新

本地改完代码后：

```bash
rsync -avz --delete \
  --exclude venv --exclude __pycache__ --exclude '*.pyc' \
  --exclude .env --exclude blog.db --exclude 'blog.db-*' \
  --exclude media --exclude backups --exclude .git \
  ./ root@blog.pum.org.cn:/srv/blog/
ssh root@blog.pum.org.cn 'cd /srv/blog && \
  sudo -u blog venv/bin/python -m scripts.manage migrate && \
  systemctl restart blog && systemctl is-active blog'
```

改了 CSS/JS 不需要重启，nginx 直接读文件（静态资源缓存 7 天，必要时改文件名或在地址后加版本号）。
重新生成代码高亮主题：`venv/bin/python -m scripts.manage export-css app/static/css/pygments.css`

## 9. 排障

| 现象 | 排查 |
| --- | --- |
| 502 Bad Gateway | `systemctl status blog`、`journalctl -u blog -n 100`，多半是 `.env` 或迁移失败 |
| 登录后又被踢回登录页 | `COOKIE_SECURE=1` 但访问的是 http；或 SECRET_KEY 每次重启变化（没配） |
| 评论验证码一直错 | 服务器时间是否准确：`timedatectl` |
| 上传大图 413 | nginx `client_max_body_size` 与 `UPLOAD_MAX_BYTES` 都要够 |
| 磁盘涨得快 | `du -sh /srv/blog/media /srv/blog/backups`，调 `--keep` |
