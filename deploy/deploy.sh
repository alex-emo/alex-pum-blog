#!/usr/bin/env bash
# 一条命令把本地代码同步到服务器并重启。
# 用法：./deploy/deploy.sh root@blog.pum.org.cn
#       REMOTE=root@1.2.3.4 ./deploy/deploy.sh
set -euo pipefail

REMOTE="${1:-${REMOTE:-}}"
if [[ -z "$REMOTE" ]]; then
  echo "用法: $0 user@host" >&2
  exit 1
fi

APP_DIR="${APP_DIR:-/srv/blog}"
SERVICE="${SERVICE:-blog}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> 同步代码到 $REMOTE:$APP_DIR"
rsync -avz --delete \
  --exclude venv --exclude __pycache__ --exclude '*.pyc' \
  --exclude .env --exclude blog.db --exclude 'blog.db-*' \
  --exclude media --exclude backups --exclude .git \
  "$HERE/" "$REMOTE:$APP_DIR/"

echo "==> 远程迁移 + 重启"
ssh "$REMOTE" "set -e
cd $APP_DIR
sudo -u blog venv/bin/python -m scripts.manage migrate
systemctl restart $SERVICE
sleep 2
systemctl is-active $SERVICE
curl -fsS http://127.0.0.1:8010/api/health
"

echo "==> 完成：https://blog.pum.org.cn"
