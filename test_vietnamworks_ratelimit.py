import time
from curl_cffi import requests

SEARCH_API_URL = "https://ms.vietnamworks.com/job-search/v1.0/search"
DETAIL_API_URL = "https://ms.vietnamworks.com/api-gateway/v1.0/tracking/job-info"

DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,vi;q=0.8",
    "origin": "https://www.vietnamworks.com",
    "referer": "https://www.vietnamworks.com/",
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

def test_vietnamworks_ratelimit(num_requests=30, delay=0.0):
    print(f"==================================================================")
    print(f"KIỂM THỬ RATE LIMIT TRÊN VIETNAMWORKS (API GATEWAY & SEARCH)")
    print(f"Số lượng requests: {num_requests} | Delay giữa các request: {delay}s")
    print(f"==================================================================")

    session = requests.Session(impersonate="chrome124")
    session.headers.update(DEFAULT_HEADERS)

    results = []
    blocked = False

    # Test xen kẽ giữa Search và Detail API để mô phỏng tải thực tế
    for i in range(1, num_requests + 1):
        t0 = time.time()
        try:
            # Lần chẵn gọi Detail API, lần lẻ gọi Search API
            if i % 2 == 0:
                endpoint_name = "Detail API"
                url = f"{DETAIL_API_URL}?jobId=2107650"
                resp = session.get(url)
            else:
                endpoint_name = "Search API"
                payload = {
                    "userId": 0,
                    "query": "software engineer",
                    "filter": [],
                    "ranges": [],
                    "order": [],
                    "hitsPerPage": 5,
                    "page": (i // 2) % 5
                }
                resp = session.post(SEARCH_API_URL, json=payload)

            duration = (time.time() - t0) * 1000
            status = resp.status_code
            
            # Check JSON status
            is_ok = False
            msg = ""
            if status == 200:
                try:
                    j = resp.json()
                    if "meta" in j and j["meta"].get("code") == 200:
                        is_ok = True
                        msg = f"OK ({j['meta'].get('nbHits')} hits)"
                    elif j.get("status") == "success":
                        is_ok = True
                        msg = "OK (job detail)"
                    else:
                        msg = f"Err: {str(j)[:40]}"
                except:
                    msg = "Non-JSON"
            else:
                msg = f"HTTP {status}"

            is_block = status in [403, 429] or "Access Denied" in resp.text or "Cloudflare" in resp.text
            
            print(f"Req #{i:02d} | [{endpoint_name:10s}] | HTTP: {status} | Latency: {duration:6.1f}ms | Result: {msg:18s} | Blocked: {is_block}")
            
            results.append({
                "req": i,
                "endpoint": endpoint_name,
                "status": status,
                "duration_ms": duration,
                "blocked": is_block
            })

            if is_block:
                print(f"\n[!] CẢNH BÁO: Bị chặn tại request #{i}!")
                print(f"    Phản hồi: {resp.text[:150]}")
                blocked = True
                break

        except Exception as e:
            print(f"Req #{i:02d} | Lỗi Exception: {e}")
            break

        if delay > 0:
            time.sleep(delay)

    print("\n---------------- TỔNG KẾT VIETNAMWORKS ----------------")
    success_count = sum(1 for r in results if r["status"] == 200 and not r["blocked"])
    avg_latency = sum(r["duration_ms"] for r in results) / len(results) if results else 0
    print(f"Thành công: {success_count}/{len(results)} requests")
    print(f"Độ trễ trung bình: {avg_latency:.1f}ms")
    print(f"Trạng thái chặn: {'BỊ CHẶN/RATE LIMIT' if blocked else 'AN TOÀN (CHƯA BỊ CHẶN)'}")

if __name__ == "__main__":
    # Bắn 30 requests liên tiếp không delay
    test_vietnamworks_ratelimit(num_requests=100, delay=0.0)
