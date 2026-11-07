#!/usr/bin/env bash
# 重启服务器后一键恢复全部服务。
# 用法（root）：bash /srv/blog/deploy/restart-all.sh
# 做四件事：nginx -> blog -> cloudflared -> 备份定时器，最后等健康检查通过。
set -uo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

say()  { printf '\n==> %s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$*"; }

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  fail "请用 root 运行：sudo bash $0"
  exit 1
fi

has_unit() { systemctl cat "$1" >/dev/null 2>&1; }

# 启动/重启一个 unit，并等待其进入 active
start_unit() {
  local unit="$1" quiet="${2:-}"
  if ! has_unit "$unit"; then
    warn "$unit 未安装，跳过"
    return 0
  fi
  systemctl enable "$unit" >/dev/null 2>&1 || true
  systemctl restart "$unit" >/dev/null 2>&1
  for _ in $(seq 1 20); do
    if systemctl is-active --quiet "$unit"; then
      ok "$unit 已启动"
      return 0
    fi
    sleep 0.5
  done
  fail "$unit 启动失败，看日志：journalctl -u $unit -n 50 --no-pager"
  [[ -n $quiet ]] || return 1
  return 1
}

say "1/4 nginx"
if command -v nginx >/dev/null 2>&1; then
  if nginx -t >/dev/null 2>&1; then
    start_unit nginx quiet || exit 1
  else
    fail "nginx 配置有误，未重启："
    nginx -t
    exit 1
  fi
else
  warn "未安装 nginx，跳过"
fi

say "2/4 blog（uvicorn）"
start_unit blog quiet || exit 1

say "3/4 cloudflared 隧道"
if has_unit cloudflared; then
  start_unit cloudflared
else
  warn "cloudflared 未安装（没有用 Cloudflare Tunnel 可忽略）"
fi

say "4/4 每日备份定时器"
if has_unit blog-backup.timer; then
  systemctl enable --now blog-backup.timer >/dev/null 2>&1 || true
  systemctl restart blog-backup.timer >/dev/null 2>&1 || true
  if systemctl is-active --quiet blog-backup.timer; then
    ok "blog-backup.timer 已启用"
  else
    warn "blog-backup.timer 未启用"
  fi
else
  warn "blog-backup.timer 未安装，跳过"
fi

say "健康检查"
health_ok=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8010/api/health >/dev/null 2>&1; then
    health_ok=1
    break
  fi
  sleep 1
done
if [[ $health_ok -eq 1 ]]; then
  ok "本地 /api/health 正常：$(curl -fsS --max-time 2 http://127.0.0.1:8010/api/health)"
else
  fail "健康检查失败，看日志：journalctl -u blog -n 80 --no-pager"
fi

echo
printf '服务状态：\n'
for unit in nginx blog cloudflared blog-backup.timer; do
  if has_unit "$unit"; then
    printf '  %-16s %s\n' "$unit" "$(systemctl is-active "$unit" 2>/dev/null || echo unknown)"
  fi
done
echo
echo "站点：https://blog.pum.org.cn  后台：https://blog.pum.org.cn/admin"
echo "日志：journalctl -u blog -f"

[[ $health_ok -eq 1 ]] || exit 1
