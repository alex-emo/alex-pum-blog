#!/usr/bin/env bash
# 用 DNS-01（阿里云 DNS API）签发证书 —— 80 端口被备案拦截时用这个
#
#   Ali_Key=<AccessKeyId> Ali_Secret=<AccessKeySecret> bash deploy/setup-dns-cert.sh
#
# 需要 RAM 子账号，授予 AliyunDNSFullAccess（或只含 pum.org.cn 的自定义策略）。
# 证书装到 nginx 已在用的 /etc/letsencrypt/live/blog.pum.org.cn/，续期由 acme.sh 定时任务负责。
set -euo pipefail

DOMAIN="${DOMAIN:-blog.pum.org.cn}"
APP_DIR="${APP_DIR:-/srv/blog}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-alex12141327@163.com}"

: "${Ali_Key:?请设置 Ali_Key（RAM 子账号 AccessKeyId）}"
: "${Ali_Secret:?请设置 Ali_Secret（AccessKeySecret）}"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "请用 root 运行"; exit 1; }

ACME="/root/.acme.sh/acme.sh"
if [ ! -x "$ACME" ]; then
  say "安装 acme.sh"
  curl -fsSL https://get.acme.sh | sh -s email="$LETSENCRYPT_EMAIL"
fi
[ -x "$ACME" ] || { echo "acme.sh 安装失败"; exit 1; }

say "使用 Let's Encrypt"
"$ACME" --set-default-ca --server letsencrypt

say "DNS-01 签发 $DOMAIN"
"$ACME" --issue --dns dns_ali -d "$DOMAIN" --keylength ec-256

say "安装证书并配置自动续期 reload"
mkdir -p /etc/letsencrypt/live/"$DOMAIN"
"$ACME" --install-cert -d "$DOMAIN" --ecc \
  --key-file       /etc/letsencrypt/live/"$DOMAIN"/privkey.pem \
  --fullchain-file /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem \
  --reloadcmd      "systemctl reload nginx"

say "校验"
nginx -t
systemctl reload nginx
"$ACME" --info -d "$DOMAIN" | tail -12
echo
echo "完成。访问 https://$DOMAIN"
echo "acme.sh 的续期任务：crontab -l | grep acme"
