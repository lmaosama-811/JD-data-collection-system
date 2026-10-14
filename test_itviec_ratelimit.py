import time
from curl_cffi import requests

def test_itviec_rate_limit(num_requests=10, delay=0.0):
    print(f"==================================================================")
    print(f"KIỂM THỬ RATE LIMIT TRÊN ITVIEC")
    print(f"Số lượng requests: {num_requests} | Delay giữa các request: {delay}s")
    print(f"==================================================================")
    
    session = requests.Session(impersonate="chrome124")
    session.headers.update({
        "authority": "itviec.com",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "referer": "https://itviec.com/"
    })

    url = "https://itviec.com/it-jobs?page=1"
    
    results = []
    blocked = False

    for i in range(1, num_requests + 1):
        t0 = time.time()
        try:
            resp = session.get(url)
            duration = (time.time() - t0) * 1000
            status = resp.status_code
            cf_ray = resp.headers.get("cf-ray", "N/A")
            is_cf_block = "Just a moment..." in resp.text or status == 403
            
            print(f"Request #{i:02d} | Status: {status} | Latency: {duration:6.1f}ms | CF-Ray: {cf_ray} | Challenge: {is_cf_block}")
            
            results.append({
                "req": i,
                "status": status,
                "duration_ms": duration,
                "challenge": is_cf_block
            })
            
            if status != 200 or is_cf_block:
                print(f"\n[!] CẢNH BÁO: Bị chặn hoặc Rate Limit tại request #{i}!")
                print(f"    Mã HTTP: {status}, Tiêu đề: {resp.text[:120].strip()}")
                blocked = True
                break
                
        except Exception as e:
            print(f"Request #{i:02d} | Lỗi Exception: {e}")
            break
            
        if delay > 0:
            time.sleep(delay)

    print("\n---------------- TỔNG KẾT ITVIEC ----------------")
    success_count = sum(1 for r in results if r["status"] == 200 and not r["challenge"])
    avg_latency = sum(r["duration_ms"] for r in results) / len(results) if results else 0
    print(f"Thành công: {success_count}/{len(results)} requests")
    print(f"Độ trễ trung bình: {avg_latency:.1f}ms")
    print(f"Trạng thái chặn: {'BỊ CHẶN/RATE LIMIT' if blocked else 'AN TOÀN (CHƯA BỊ CHẶN)'}")

if __name__ == "__main__":
    # Test Burst: Gửi liên tiếp 10 request không delay
    test_itviec_rate_limit(num_requests=30, delay=0.0)
