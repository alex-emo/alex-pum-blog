#!/usr/bin/env bash
# 安装 Cloudflare Origin Certificate（CF 回源用，15 年有效期，不用续期）
# 用法（root）：
#   bash deploy/install-cf-origin-cert.sh /root/cf-origin.pem /root/cf-origin.key
set -euo pipefail
DOMAIN="${DOMAIN:-blog.pum.org.cn}"
CRT="${1:?证书路径}"; KEY="${2:?私钥路径}"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
[ "$(id -u)" -eq 0 ] || { echo "请用 root"; exit 1; }
[ -s "$CRT" ] && [ -s "$KEY" ] || { echo "证书或私钥为空"; exit 1; }

openssl x509 -in "$CRT" -noout -subject -issuer -enddate
install -d -m 755 /etc/letsencrypt/live/"$DOMAIN"
install -m 644 "$CRT" /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem
install -m 600 "$KEY" /etc/letsencrypt/live/"$DOMAIN"/privkey.pem
nginx -t
systemctl reload nginx
echo "已安装，测试：curl -sI https://$DOMAIN | head -3"
