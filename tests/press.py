import requests
import time
import random
import threading
import socket
from concurrent.futures import ThreadPoolExecutor

# ================= 🚨 关键补丁：强制使用 IPv4 🚨 =================
# 获取原生的 getaddrinfo 方法
orig_getaddrinfo = socket.getaddrinfo
# 重写这个方法，强制只请求 IPv4 (AF_INET)
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4
# =================================================================

# ================= 配置区 =================
BASE_URL = "https://blog.pum.org.cn/"
CONCURRENCY = 30      # 并发数
TOTAL_REQUESTS = 1000 # 压测总数
# ==========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:159.0) Gecko/20100101 Firefox/159.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

lock = threading.Lock()
success_count = 0
fail_count = 0
status_codes = {}

def send_request(req_id):
    global success_count, fail_count
    
    # 加随机参数破 CDN 缓存
    url = f"{BASE_URL}?stress_test={random.randint(1, 99999999)}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        status = response.status_code
        
        with lock:
            status_codes[status] = status_codes.get(status, 0) + 1
            if status == 200:
                success_count += 1
            else:
                fail_count += 1
                
            if (success_count + fail_count) % 100 == 0:
                print(f"⏳ 进度: {success_count + fail_count}/{TOTAL_REQUESTS} | 成功: {success_count} | 失败(或拦截): {fail_count}", flush=True)
                
    except Exception as e:
        with lock:
            fail_count += 1
            status_codes["NetworkError"] = status_codes.get("NetworkError", 0) + 1
            if (success_count + fail_count) % 100 == 0:
                print(f"⏳ 进度: {success_count + fail_count}/{TOTAL_REQUESTS} | 成功: {success_count} | 失败: {fail_count}", flush=True)

if __name__ == "__main__":
    print(f"🔥 开始压测: {BASE_URL}")
    print(f"🚀 并发数: {CONCURRENCY} | 总请求数: {TOTAL_REQUESTS}")
    print("--------------------------------------------------")
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        for i in range(TOTAL_REQUESTS):
            executor.submit(send_request, i)
            
    end_time = time.time()
    duration = end_time - start_time
    
    print("--------------------------------------------------")
    print(f"✅ 压测完成！总耗时: {duration:.2f} 秒")
    print(f"⚡ QPS (每秒处理请求数): {TOTAL_REQUESTS / duration:.2f}")
    print("📊 状态码统计分布:")
    for code, count in status_codes.items():
        print(f"   - HTTP {code}: {count} 次")
