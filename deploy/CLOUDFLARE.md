# Cloudflare 全站代理（不备案的应急方案）

> 前提：源站已有 Let's Encrypt 证书（`bash deploy/setup-alpn-cert.sh`），CF 才能用 Full (strict)。
> 注意：大陆服务器未备案用 CF 代理属于绕备案，可能被封；长期建议换香港服务器。

## 1. 源站证书

```bash
openssl x509 -in /etc/letsencrypt/live/blog.pum.org.cn/fullchain.pem -noout -issuer -enddate
```

`issuer` 要是 `Let's Encrypt`。不是就先跑 `bash deploy/setup-alpn-cert.sh`。

## 2. 域名托管到 Cloudflare

1. Cloudflare → Add a site → `pum.org.cn` → 选 Free
2. 记下分配的两个 NS，例如 `ada.ns.cloudflare.com` / `bob.ns.cloudflare.com`
3. 阿里云域名控制台 → 域名列表 → `pum.org.cn` → DNS 修改 → 使用自定义 DNS → 填这两个
4. 生效检查（本地跑）：`dig NS pum.org.cn +short @8.8.8.8`

## 3. Cloudflare 解析与 SSL

- DNS：`A blog` → `47.117.51.245`（或当前公网 IP），**Proxy status 橙色云**
- SSL/TLS → Overview → **Full (strict)**
- SSL/TLS → Edge Certificates → 打开 **Always Use HTTPS**
- （可选）Rules → Redirect Rules 把 `http://` 强制到 `https://`

## 4. 验证

```bash
curl -sI https://blog.pum.org.cn | grep -i -E 'cf-ray|server'
```

出现 `cf-ray` 说明已走 CF；`server: cloudflare`。

## 5. 可选加固：源站只接受 Cloudflare

```bash
# 拉取官方 IP 段并只放行 CF 到 443（保留 SSH）
for ip in $(curl -s https://www.cloudflare.com/ips-v4); do ufw allow from $ip to any port 443 proto tcp; done
```

配完务必先确认 CF 回源正常，再关掉 443 对全网的放行，否则容易把自己锁在外面。
