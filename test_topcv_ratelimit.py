import time
from curl_cffi import requests

CSRF_TOKEN = "4aB5lyZcRpQDq0uv4NYS7R9IXNO8y4L1NtUzWRxC"

COOKIE_STR = """client_id=b0a55e68-5c7b-4794-83a1-c959cd61e345; _fbp=fb.1.1791472229527.358756137540049194; _tt_enable_cookie=1; _ttp=01M4E11Q7JF9WAWC3X56XQAZF1_.tt.1.1791472229619; _taid=CvJRgDdY7k.1791472631998; _ga_LPTX3SET7M=GS2.1.s1791518703$o3$g1$t1791519439$j60$l0$h0; _ga_QWDMETS517=GS2.1.s1791534293$o1$g0$t1791534296$j57$l0$h0$dMuu1zTnbgf9tBGZumLjx5BGWoV3EH112Vw; _tafp=45b49dffab230f09010ae24a39780c98; _tasid=izUH7mWPkf.1791875710298; _gid=GA1.2.282136320.1791875710; _clck=1g202o7%5E2%5Ega9%5E0%5E2472; appier=%7B%22event%22%3A%22job_searched%22%2C%22payload%22%3A%7B%22searched_keyword%22%3A%22%22%2C%22job_category%22%3A%22%22%2C%22company_category%22%3A%22%22%2C%22work_location%22%3A%22%22%7D%7D; _gcl_au=1.1.1198582981.1791472229.-.-.1791472229.2016099811.1791875710.1791876484; _ga=GA1.2.2044867686.1791472229; _clsk=1epvr3m%5E1791876486758%5E3%5E0%5Eg.clarity.ms%2Fcollect; g_state={"i_l":0,"i_ll":1791876497008,"i_e":{"enable_itp_optimization":24},"i_et":1791876497008,"i_b":"MrnCNe7zt6AVfj8hOADeE8v+4/5X3c9t9QZ3loiXaH8"}; cf_clearance=Tb3weQu2jsYtqCTGvV9bPEJa_ROgqiuaxq6EYRmoEYc-1791876529-1.2.1.1-57GsN8oG.iobB4_hXsHrQUVFuzBKw8K5zIlUg2CVzQbCEaPRJdFd22hwYmJbb7czHCB2IsOvjG6mPAEH9VY0dIwCNQtr2ohOh65ij9IDGMxQJKjmnGJmFXTboBaCuuie83MgubcmZMWqOWx99fan6vf0Q_BZyyhHCGNZg7aE.2Xt3ZLpLlTNrhO9rViF36vY2gGD.WaDpmz8PwvAWhpelIcVBum1c.z7OZJLnngn4bXQR2dSlKYv447eR6hs09y1uecJY6zE07FohRdvb6irVm64Og3PepgV9RS5UvAfSbLEMu0ZS3tjslXdB8Sb18SmG8vsoK55DTh6Lmh15YjWc8JFAskXdrrrFNfY6EPkTcr.KFiwXmiA7l6gB057iGlH4aSuP_0VbsFoUZz13xf76.AFnR2KYZt.kEtCED0t1Lo; ttcsid_D0FPAFRC77UA600KP0E0=1791875710756::3p2q6UXMNuKKJ74XwK4K.4.1791876580051.1; _tasla=1791876585550; is_save_log_keyword=true; _ga_F385SHE0Y3=GS2.1.s1791875709$o4$g1$t1791876589$j51$l0$h13154843$dQpDAodY6E9hjRgmcrtLpkXOZzabzUMnT5A; ref_source_tracking_id=eyJpdiI6IlpkTTUxK2x5MDYyelNlTVRGRWVaQXc9PSIsInZhbHVlIjoicWdVMXIxa2xoMUxOUGRMVThqcDdrQmZuWkRQQURFeXpLZUs0OFd3RDM5b2llR0h4dUxTZjdiMXRrY2Zvc0VHeHVSQzUwdkUyYXdwdXVEM1YzSkxvMTBpR09DVmcwb1N6V0t2UnhydWE4cDA9IiwibWFjIjoiZTNiNzM5NjFmYjYxZDZkN2EzNjkyZWZiNWI4ODdhMmY1YzdhZDhmMjQ3MjhhNWU2MDVmY2E3MTBhYmY4MmE3NyIsInRhZyI6IiJ9; XSRF-TOKEN=eyJpdiI6IlBRUXRwclhqVmwvV211bGRvQUNDNnc9PSIsInZhbHVlIjoiNG1CMU5VaDhjTlNwWkNuczQ4Uy9mbFNsbksySnc4MWlJT3RyTWYrMGtyNy9jbS9JRmpmRmhEZ09TQjFBNFd3K21DaUVKdng5anFlWVI4L0hJS21COTljRjhiQjJhWXl4SzR6Z3dDeGVVdEN6ZzZFWFF3Qm5oQWpUTlBkeG4vUzYiLCJtYWMiOiI0M2JhZDNlOTk2M2U1MDhlOTRkYzI5NzU1MDNhNDkyY2Y4YjllNTdhZGNmNmQ2NWY5MmNmYTQyMGViMTEwNWZmIiwidGFnIjoiIn0%3D; topcv_session=eyJpdiI6Im5vVUx5bmlnN09OZ1g3U0FmTmNabWc9PSIsInZhbHVlIjoiV2VTWVU5VzFKYXRFM0NEMENqVy9VY3lCRGloSHBPZ0p0ejNpeTBVUUlqb3lrLzNvSDJmTWdEeHJqYzlhWGM3TlYwb3pPS0ZjVUg0M1BVWVBVRnFYKzBjOVZMaHcrREgxc3psNHRKZlRLNWNGVDVrc05oS2ZkMFdQdThTVFFBNmYiLCJtYWMiOiI2ZGYxMzAzNjIyMzNhOGVhZjIyNmQ4NDBmOTEzZWQ2YmU4MmIwYjE4MjQ4MDEyZjZmZWE5N2UxODUxN2JjMTEzIiwidGFnIjoiIn0%3D; ttcsid=1791875710757::ii7wqvjY0-wvg8_Bn0Sf.4.1791876580051.0::1.880026.775707::878584.9.348.202::878943.30.77"""

COMMON_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"

def test_topcv_rate_limit(num_requests=10, delay=0.0):
    print(f"==================================================================")
    print(f"KIỂM THỬ RATE LIMIT TRÊN TOPCV (SEARCH API POST)")
    print(f"Số lượng requests: {num_requests} | Delay giữa các request: {delay}s")
    print(f"==================================================================")

    session = requests.Session(impersonate="chrome124")
    cookies = {item.split("=")[0]: item.split("=")[1] for item in COOKIE_STR.strip().split("; ") if "=" in item}
    session.cookies.update(cookies)
    
    session.headers.update({
        "authority": "www.topcv.vn",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "sec-ch-ua": '"Google Chrome";v="155", "Chromium";v="155", "Not(A:Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "user-agent": COMMON_USER_AGENT,
        "accept": "application/json, text/javascript, */*; q=0.01",
        "x-requested-with": "XMLHttpRequest",
        "x-csrf-token": CSRF_TOKEN,
        "origin": "https://www.topcv.vn",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    })

    url = "https://www.topcv.vn/tim-viec-lam-software-engineer?page=1&type_keyword=1&sba=1&saturday_status=0"
    session.headers["referer"] = url

    results = []
    blocked = False

    for i in range(1, num_requests + 1):
        t0 = time.time()
        try:
            resp = session.post(url, data=b"")
            duration = (time.time() - t0) * 1000
            status = resp.status_code
            cf_ray = resp.headers.get("cf-ray", "N/A")
            
            # Check JSON status if 200
            json_status = "N/A"
            if status == 200:
                try:
                    j = resp.json()
                    json_status = j.get("status", "unknown")
                except:
                    json_status = "not-json"

            is_block = status in [403, 429] or "Attention Required" in resp.text
            
            print(f"Request #{i:02d} | HTTP: {status} | JSON: {json_status:7s} | Latency: {duration:6.1f}ms | CF-Ray: {cf_ray} | Blocked: {is_block}")
            
            results.append({
                "req": i,
                "status": status,
                "json_status": json_status,
                "duration_ms": duration,
                "blocked": is_block
            })

            if is_block or json_status != "success":
                print(f"\n[!] CẢNH BÁO: Bị chặn hoặc Rate Limit tại request #{i}!")
                print(f"    Phản hồi: {resp.text[:150].strip()}")
                blocked = True
                break

        except Exception as e:
            print(f"Request #{i:02d} | Exception: {e}")
            break

        if delay > 0:
            time.sleep(delay)

    print("\n---------------- TỔNG KẾT TOPCV ----------------")
    success_count = sum(1 for r in results if r["status"] == 200 and r["json_status"] == "success")
    avg_latency = sum(r["duration_ms"] for r in results) / len(results) if results else 0
    print(f"Thành công: {success_count}/{len(results)} requests")
    print(f"Độ trễ trung bình: {avg_latency:.1f}ms")
    print(f"Trạng thái chặn: {'BỊ CHẶN/RATE LIMIT' if blocked else 'AN TOÀN (CHƯA BỊ CHẶN)'}")

if __name__ == "__main__":
    # Test Burst: Gửi liên tiếp 10 request POST không delay
    test_topcv_rate_limit(num_requests=30, delay=0.0)
