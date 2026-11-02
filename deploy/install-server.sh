#!/usr/bin/env bash
# 一键部署：Debian 12 / Ubuntu（root 执行）
#
#   git clone https://github.com/alex-emo/alex-pum-blog.git /srv/blog
#   bash /srv/blog/deploy/install-server.sh
#
# 可选环境变量：
#   DOMAIN=blog.pum.org.cn  APP_DIR=/srv/blog  APP_USER=blog  ADMIN_USER=pum
#   LETSENCRYPT_EMAIL=you@example.com  ENABLE_HTTPS=0  （0=先不签证书）
set -euo pipefail

DOMAIN="${DOMAIN:-blog.pum.org.cn}"
APP_DIR="${APP_DIR:-/srv/blog}"
APP_USER="${APP_USER:-blog}"
ADMIN_USER="${ADMIN_USER:-pum}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-alex12141327@163.com}"
ENABLE_HTTPS="${ENABLE_HTTPS:-1}"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m错误: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 运行"

# 部分精简镜像 root 的 PATH 不含 /usr/sbin、/sbin（useradd/swapon 找不到）
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
[ -f "$APP_DIR/app/main.py" ] || die "代码不在 $APP_DIR，请先 git clone 到该目录"
command -v apt-get >/dev/null || die "只支持 Debian/Ubuntu"

say "1/9 安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx sqlite3 rsync ufw certbot curl sudo util-linux passwd

say "2/9 内存不足 2G 时加 swap"
if ! swapon --show | grep -q .; then
  if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
    chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "已创建 2G swap"
  fi
else
  echo "已有 swap，跳过"
fi

if [ "$APP_USER" != "blog" ]; then
  die "deploy/blog.service 里写死了 User=blog，APP_USER 请保持默认"
fi

say "3/9 建运行用户与目录"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR/media" "$APP_DIR/backups"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
usermod -aG "$APP_USER" www-data   # nginx 需要读 media（UMask=0027 生成 640 文件）
systemctl restart nginx

say "4/9 创建 venv 并安装依赖"
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
fi
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

say "5/9 生成 .env"
if [ -f "$APP_DIR/.env" ]; then
  echo ".env 已存在，跳过（如需重建请先备份后删除）"
else
  SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
  cat > "$APP_DIR/.env" <<EOF
SITE_NAME=Pum 的博客
SITE_DESCRIPTION=记录技术、折腾与日常。
SITE_URL=https://$DOMAIN
SITE_AUTHOR=Pum
SITE_SIGNATURE=我们必须相信西西弗斯是自由的。
SITE_AVATAR=/static/img/avatar.png
SITE_EMAIL=alex12141327@163.com
SITE_X=ParameciumAlex
SITE_TELEGRAM=praeity
SITE_TIMEZONE=Asia/Shanghai
SECRET_KEY=$SECRET_KEY
COOKIE_SECURE=1
DEBUG=0
PAGE_SIZE=10
COMMENT_REQUIRE_APPROVAL=0
COMMENT_RATE_SECONDS=30
COMMENT_ATTEMPTS_PER_HOUR=40
EOF
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "已写入 $APP_DIR/.env（SECRET_KEY 随机生成）"
fi

say "6/9 初始化数据库"
sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && venv/bin/python -m scripts.manage migrate"

say "7/9 创建管理员（已存在则跳过）"
HAS_ADMIN="$(sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && venv/bin/python - <<'PY'
from sqlalchemy import select
from app.database import SessionLocal
from app.models import AdminUser
with SessionLocal() as db:
    print(1 if db.execute(select(AdminUser.id).limit(1)).first() else 0)
PY
")"
if [ "$HAS_ADMIN" = "1" ]; then
  echo "已有管理员，跳过。改密码：cd $APP_DIR && sudo -u $APP_USER venv/bin/python -m scripts.manage reset-password <用户名>"
else
  echo "为管理员 $ADMIN_USER 设置密码（至少 8 位）"
  sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && venv/bin/python -m scripts.manage create-admin '$ADMIN_USER'"
fi

say "8/9 systemd 服务"
install -m 644 "$APP_DIR/deploy/blog.service" /etc/systemd/system/blog.service
systemctl daemon-reload
systemctl enable --now blog
systemctl is-active blog >/dev/null || die "blog 服务没起来，看 journalctl -u blog -n 100"
# 首次启动要跑迁移，等最多 30 秒
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8010/api/health >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:8010/api/health >/dev/null || die "健康检查失败，看 journalctl -u blog -n 100"
echo "uvicorn 已在 127.0.0.1:8010 运行"

git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
say "9/9 nginx + HTTPS"
install -m 644 "$APP_DIR/deploy/nginx-blog.conf" /etc/nginx/sites-available/blog
ln -sf /etc/nginx/sites-available/blog /etc/nginx/sites-enabled/blog
rm -f /etc/nginx/sites-enabled/default
mkdir -p /var/www/html /etc/letsencrypt/live/"$DOMAIN"

# 先放自签证书占位，让 nginx -t 通过
if [ ! -f /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem ]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj "/CN=$DOMAIN" \
    -keyout /etc/letsencrypt/live/"$DOMAIN"/privkey.pem \
    -out /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem 2>/dev/null
fi
nginx -t
systemctl reload nginx
ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 'Nginx Full' >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

if [ "$ENABLE_HTTPS" = "1" ] && getent hosts "$DOMAIN" >/dev/null; then
  echo "申请 Let's Encrypt 证书：$DOMAIN"
  certbot certonly --webroot -w /var/www/html -d "$DOMAIN" \
    -m "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email --non-interactive || \
    echo "certbot 失败，见上方输出（DNS 未生效/80 被墙最常见）"
  nginx -t && systemctl reload nginx
  mkdir -p /etc/letsencrypt/renewal-hooks/deploy
  printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
  chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
else
  echo "跳过证书签发（ENABLE_HTTPS=0 或 $DOMAIN 尚未解析到本机）"
  echo "DNS 生效后重跑：ENABLE_HTTPS=1 bash $APP_DIR/deploy/install-server.sh"
fi

install -m 644 "$APP_DIR/deploy/blog-backup.service" /etc/systemd/system/blog-backup.service
install -m 644 "$APP_DIR/deploy/blog-backup.timer" /etc/systemd/system/blog-backup.timer
systemctl daemon-reload
systemctl enable --now blog-backup.timer

say "部署完成"
cat <<EOF

  站点：   http://$DOMAIN  （证书签发成功则 https）
  本地检查：curl -I http://127.0.0.1:8010/api/health
  后台：   http://$DOMAIN/admin
  日志：   journalctl -u blog -f
  更新：   cd $APP_DIR && git pull && sudo -u $APP_USER venv/bin/pip install -r requirements.txt && sudo -u $APP_USER venv/bin/python -m scripts.manage migrate && systemctl restart blog
  备份：   $APP_DIR/backups/（每天 03:30，保留 14 天）

EOF
