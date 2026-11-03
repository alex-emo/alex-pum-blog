# 部署到 blog.pum.org.cn

## 最快路径（推荐）

服务器上以 root 执行：

```bash
apt-get update && apt-get install -y git
git clone https://github.com/alex-emo/alex-pum-blog.git /srv/blog
bash /srv/blog/deploy/install-server.sh
```

脚本会完成：依赖安装、swap、建用户、venv、`.env`（随机 SECRET_KEY）、迁移、建管理员（交互输密码）、
systemd、nginx、自签证书占位、certbot 签发、防火墙、每日备份定时器。

前提：`blog.pum.org.cn` 的 A 记录已指向本机，80/443 在安全组放行。DNS 未生效时脚本会跳过 certbot，
稍后重跑 `ENABLE_HTTPS=1 bash /srv/blog/deploy/install-server.sh` 即可。

下面的分步说明是脚本的等价手工流程，出问题时可以对照着排查。

## 中国大陆无备案：用 Cloudflare Tunnel（当前线上方案）

阿里云大陆节点未备案时，80 端口被劫持成 `Non-compliance ICP Filing` 403，443 入站 TLS 会被按 SNI 重置
（CF 回源表现为 525）。可行方案是 **Cloudflare Tunnel**：源站主动出站连 CF，不需要任何入站端口。

服务器上：

```bash
curl -fsSL -o /tmp/cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i /tmp/cloudflared.deb
cloudflared service install <CF 隧道 token>
systemctl status cloudflared --no-pager
```

CF 控制台（零信任 → 网络 → 隧道）：

1. 创建隧道，连接器选 Cloudflared，复制 token（就是上面那条）
2. 隧道 → 添加路由 → 已发布的应用程序 → 子域 `blog`、域 `pum.org.cn`、服务 `http://127.0.0.1:8010`
3. 保存后 CF 自动建 CNAME `blog.pum.org.cn → <隧道ID>.cfargotunnel.com`（代理保持橙色云）

此时 `https://blog.pum.org.cn` 由 CF 边缘提供证书，源站 80/443 可以全部关闭：
直接访问 IP 会绕过 CF，建议在安全组只放行 22。

隧道配置是 CF 托管（remote-managed），改路由不需要动服务器文件。

---


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

## 只允许域名访问（禁止 IP 直接访问）

`deploy/nginx-blog.conf` 开头有两个 `default_server`：未匹配 `blog.pum.org.cn` 的请求（包括直接用 IP 访问）一律 `return 444` 断开。更新配置后：

```bash
git config --global --add safe.directory /srv/blog   # 仓库属主是 blog，root 跑 git 需要
cd /srv/blog && git pull
install -m 644 deploy/nginx-blog.conf /etc/nginx/sites-available/blog
nginx -t && systemctl reload nginx
curl -I http://<服务器IP>/      # 应连接被重置/无响应
```

## 80 被备案拦截时：DNS-01 签发（阿里云 DNS）

阿里云对「未接入备案」的域名会在 80 端口返回 `Server: Beaver` 的 403，HTTP-01 无法完成。改用 DNS-01，不依赖 80：

1. 阿里云 RAM 建子账号（勾选 OpenAPI 调用），授权 `AliyunDNSFullAccess`（更稳妥是自定义策略只允许改 `pum.org.cn`）
2. 服务器上执行（AK 不要提交到仓库）：

```bash
cd /srv/blog && git pull
Ali_Key=<AccessKeyId> Ali_Secret=<AccessKeySecret> bash deploy/setup-dns-cert.sh
```

证书装到 `/etc/letsencrypt/live/blog.pum.org.cn/`（nginx 已在用这两个路径），acme.sh 自带每日续期与 reload。之后仍建议把备案接入阿里云，80 才能正常跳转 HTTPS。

## 80 被备案拦截时：TLS-ALPN-01（最省事）

不碰 80、不改 DNS、不要 API 密钥。Let's Encrypt 直连 443 做 TLS 校验，签发时短暂停 nginx：

```bash
cd /srv/blog && git pull
bash deploy/setup-alpn-cert.sh
```

如果阿里云对未备案域名的 443 也做了拦截（握手就断），则改用 DNS-01：`bash deploy/setup-dns-cert.sh`（需要 RAM AccessKey）。
