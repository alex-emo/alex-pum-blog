#!/usr/bin/env bash
# 用 TLS-ALPN-01 签发证书：不需要 80 端口、不需要 DNS API、不需要改解析。
# 原理：Let's Encrypt 直连 443 做 TLS 握手校验，期间临时停掉 nginx 让 acme.sh 占用 443。
#
#   bash deploy/setup-alpn-cert.sh
set -euo pipefail

DOMAIN="${DOMAIN:-blog.pum.org.cn}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-alex12141327@163.com}"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "请用 root 运行"; exit 1; }

ACME="/root/.acme.sh/acme.sh"
if [ ! -x "$ACME" ]; then
  say "安装 acme.sh"
  curl -fsSL https://get.acme.sh | sh -s email="$LETSENCRYPT_EMAIL"
fi
[ -x "$ACME" ] || { echo "acme.sh 安装失败"; exit 1; }

command -v socat >/dev/null 2>&1 || { say "安装 socat（TLS-ALPN 需要）"; apt-get update -qq && apt-get install -y -qq socat; }

say "使用 Let's Encrypt"
"$ACME" --set-default-ca --server letsencrypt

say "TLS-ALPN-01 签发 $DOMAIN（会短暂停 nginx）"
"$ACME" --issue --alpn -d "$DOMAIN" --keylength ec-256 \
  --pre-hook  "systemctl stop nginx" \
  --post-hook "systemctl start nginx"

say "安装证书到 nginx 正在使用的路径"
mkdir -p /etc/letsencrypt/live/"$DOMAIN"
"$ACME" --install-cert -d "$DOMAIN" --ecc \
  --key-file       /etc/letsencrypt/live/"$DOMAIN"/privkey.pem \
  --fullchain-file /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem \
  --reloadcmd      "systemctl reload nginx"

systemctl start nginx 2>/dev/null || true
nginx -t
systemctl reload nginx
"$ACME" --info -d "$DOMAIN" | tail -12
echo
echo "完成。访问 https://$DOMAIN"
