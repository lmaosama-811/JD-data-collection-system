import json
import re
import time
from bs4 import BeautifulSoup, SoupStrainer
from curl_cffi import requests

# ==============================================================================
# 1. CẤU HÌNH PHIÊN & XÁC THỰC
# ==============================================================================
CSRF_TOKEN = "4aB5lyZcRpQDq0uv4NYS7R9IXNO8y4L1NtUzWRxC"

COOKIE_STR = """client_id=b0a55e68-5c7b-4794-83a1-c959cd61e345; _fbp=fb.1.1791472229527.358756137540049194; _tt_enable_cookie=1; _ttp=01M4E11Q7JF9WAWC3X56XQAZF1_.tt.1.1791472229619; _taid=CvJRgDdY7k.1791472631998; _ga_LPTX3SET7M=GS2.1.s1791518703$o3$g1$t1791519439$j60$l0$h0; _ga_QWDMETS517=GS2.1.s1791534293$o1$g0$t1791534296$j57$l0$h0$dMuu1zTnbgf9tBGZumLjx5BGWoV3EH112Vw; _tafp=45b49dffab230f09010ae24a39780c98; _tasid=izUH7mWPkf.1791875710298; _gid=GA1.2.282136320.1791875710; _clck=1g202o7%5E2%5Ega9%5E0%5E2472; appier=%7B%22event%22%3A%22job_searched%22%2C%22payload%22%3A%7B%22searched_keyword%22%3A%22%22%2C%22job_category%22%3A%22%22%2C%22company_category%22%3A%22%22%2C%22work_location%22%3A%22%22%7D%7D; _gcl_au=1.1.1198582981.1791472229.-.-.1791472229.2016099811.1791875710.1791876484; _ga=GA1.2.2044867686.1791472229; _clsk=1epvr3m%5E1791876486758%5E3%5E0%5Eg.clarity.ms%2Fcollect; g_state={"i_l":0,"i_ll":1791876497008,"i_e":{"enable_itp_optimization":24},"i_et":1791876497008,"i_b":"MrnCNe7zt6AVfj8hOADeE8v+4/5X3c9t9QZ3loiXaH8"}; cf_clearance=Tb3weQu2jsYtqCTGvV9bPEJa_ROgqiuaxq6EYRmoEYc-1791876529-1.2.1.1-57GsN8oG.iobB4_hXsHrQUVFuzBKw8K5zIlUg2CVzQbCEaPRJdFd22hwYmJbb7czHCB2IsOvjG6mPAEH9VY0dIwCNQtr2ohOh65ij9IDGMxQJKjmnGJmFXTboBaCuuie83MgubcmZMWqOWx99fan6vf0Q_BZyyhHCGNZg7aE.2Xt3ZLpLlTNrhO9rViF36vY2gGD.WaDpmz8PwvAWhpelIcVBum1c.z7OZJLnngn4bXQR2dSlKYv447eR6hs09y1uecJY6zE07FohRdvb6irVm64Og3PepgV9RS5UvAfSbLEMu0ZS3tjslXdB8Sb18SmG8vsoK55DTh6Lmh15YjWc8JFAskXdrrrFNfY6EPkTcr.KFiwXmiA7l6gB057iGlH4aSuP_0VbsFoUZz13xf76.AFnR2KYZt.kEtCED0t1Lo; ttcsid_D0FPAFRC77UA600KP0E0=1791875710756::3p2q6UXMNuKKJ74XwK4K.4.1791876580051.1; _tasla=1791876585550; is_save_log_keyword=true; _ga_F385SHE0Y3=GS2.1.s1791875709$o4$g1$t1791876589$j51$l0$h13154843$dQpDAodY6E9hjRgmcrtLpkXOZzabzUMnT5A; ref_source_tracking_id=eyJpdiI6IlpkTTUxK2x5MDYyelNlTVRGRWVaQXc9PSIsInZhbHVlIjoicWdVMXIxa2xoMUxOUGRMVThqcDdrQmZuWkRQQURFeXpLZUs0OFd3RDM5b2llR0h4dUxTZjdiMXRrY2Zvc0VHeHVSQzUwdkUyYXdwdXVEM1YzSkxvMTBpR09DVmcwb1N6V0t2UnhydWE4cDA9IiwibWFjIjoiZTNiNzM5NjFmYjYxZDZkN2EzNjkyZWZiNWI4ODdhMmY1YzdhZDhmMjQ3MjhhNWU2MDVmY2E3MTBhYmY4MmE3NyIsInRhZyI6IiJ9; XSRF-TOKEN=eyJpdiI6IlBRUXRwclhqVmwvV211bGRvQUNDNnc9PSIsInZhbHVlIjoiNG1CMU5VaDhjTlNwWkNuczQ4Uy9mbFNsbksySnc4MWlJT3RyTWYrMGtyNy9jbS9JRmpmRmhEZ09TQjFBNFd3K21DaUVKdng5anFlWVI4L0hJS21COTljRjhiQjJhWXl4SzR6Z3dDeGVVdEN6ZzZFWFF3Qm5oQWpUTlBkeG4vUzYiLCJtYWMiOiI0M2JhZDNlOTk2M2U1MDhlOTRkYzI5NzU1MDNhNDkyY2Y4YjllNTdhZGNmNmQ2NWY5MmNmYTQyMGViMTEwNWZmIiwidGFnIjoiIn0%3D; topcv_session=eyJpdiI6Im5vVUx5bmlnN09OZ1g3U0FmTmNabWc9PSIsInZhbHVlIjoiV2VTWVU5VzFKYXRFM0NEMENqVy9VY3lCRGloSHBPZ0p0ejNpeTBVUUlqb3lrLzNvSDJmTWdEeHJqYzlhWGM3TlYwb3pPS0ZjVUg0M1BVWVBVRnFYKzBjOVZMaHcrREgxc3psNHRKZlRLNWNGVDVrc05oS2ZkMFdQdThTVFFBNmYiLCJtYWMiOiI2ZGYxMzAzNjIyMzNhOGVhZjIyNmQ4NDBmOTEzZWQ2YmU4MmIwYjE4MjQ4MDEyZjZmZWE5N2UxODUxN2JjMTEzIiwidGFnIjoiIn0%3D; ttcsid=1791875710757::ii7wqvjY0-wvg8_Bn0Sf.4.1791876580051.0::1.880026.775707::878584.9.348.202::878943.30.77"""

COMMON_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"

def create_crawler_session() -> requests.Session:
    """Khởi tạo phiên curl_cffi với cấu hình giả lập trình duyệt Chrome"""
    session = requests.Session(impersonate="chrome124")
    
    # Nạp cookies từ chuỗi cookie trình duyệt
    cookies = {}
    for item in COOKIE_STR.strip().split("; "):
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k] = v
    session.cookies.update(cookies)
    
    # Thiết lập headers mặc định
    session.headers.update({
        "authority": "www.topcv.vn",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "sec-ch-ua": '"Google Chrome";v="155", "Chromium";v="155", "Not(A:Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "user-agent": COMMON_USER_AGENT
    })
    return session

# ==============================================================================
# 2. BƯỚC 1 & 2: GỌI API TÌM KIẾM & BÓC TÁCH URL VIỆC LÀM
# ==============================================================================
def search_jobs(session: requests.Session, keyword="software-engineer", page=1):
    print(f"\n==================================================================")
    print(f"[Bước 1] Gửi API POST tìm kiếm: '{keyword}' (Trang {page}) bằng curl_cffi")
    print(f"==================================================================")

    url = f"https://www.topcv.vn/tim-viec-lam-{keyword}?page={page}&type_keyword=1&sba=1&saturday_status=0"
    
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "origin": "https://www.topcv.vn",
        "referer": url,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-csrf-token": CSRF_TOKEN,
        "x-requested-with": "XMLHttpRequest"
    }

    t0 = time.time()
    response = session.post(url, headers=headers, data=b"")
    req_time = time.time() - t0

    if response.status_code != 200:
        print(f"[!] Lỗi kết nối API. HTTP Status: {response.status_code}")
        if response.status_code in [403, 419]:
            print("[!] Token hoặc Cookie Cloudflare (cf_clearance) đã hết hạn.")
        return []

    data = response.json()
    if data.get("status") != "success":
        print(f"[!] Server trả về trạng thái thất bại: {data.get('status')}")
        return []

    job_data = data.get("data", {})
    html_job = job_data.get("html_job", "")
    total = job_data.get("total", 0)
    print(f"[✔] Nhận kết quả thành công trong {req_time:.2f}s! Tổng số việc làm: {total}")

    print(f"\n[Bước 2] Bóc tách danh sách URL việc làm từ 'html_job'")
    # Dùng SoupStrainer để chỉ lọc các thẻ <a> có href chứa link việc làm
    link_strainer = SoupStrainer("a", href=True)
    soup = BeautifulSoup(html_job, "lxml", parse_only=link_strainer)
    
    job_map = {}
    for a in soup.find_all("a"):
        href = a["href"].split("?")[0].strip()
        if "topcv.vn/viec-lam/" in href:
            title = a.get_text(strip=True)
            if href not in job_map and title:
                job_map[href] = title

    job_list = [{"title": t, "url": u} for u, t in job_map.items()]
    print(f"[✔] Đã bóc tách được {len(job_list)} công việc:")
    for idx, item in enumerate(job_list[:5], 1):
        print(f"  {idx}. {item['title']}\n     URL: {item['url']}")

    return job_list

# ==============================================================================
# 3. BƯỚC 3 & 4: LẤY JSON-LD (REGEX) & BỔ SUNG TỪ DOM (SOUPSTRAINER)
# ==============================================================================
def crawl_job_detail(session: requests.Session, job_url: str):
    print(f"\n--> Đang tải chi tiết: {job_url}")
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1"
    }

    t0 = time.time()
    resp = session.get(job_url, headers=headers)
    dl_time = time.time() - t0
    
    if resp.status_code != 200:
        print(f"[!] Không thể tải trang. Mã lỗi: {resp.status_code}")
        return None

    html = resp.text
    print(f"    + Tải trang hoàn tất: {len(html)} ký tự ({dl_time:.2f}s)")

    # -------------------------------------------------------------
    # [CẢI TIẾN 1]: Bóc tách <script type="application/ld+json"> bằng REGEX
    # Tốc độ: ~1-2 mili-giây, không cần parse cây DOM
    # -------------------------------------------------------------
    t_reg_start = time.time()
    ld_pattern = r'<script[^>]*type=[\'\"]application/ld\+json[\'\"][^>]*>(.*?)</script>'
    ld_matches = re.findall(ld_pattern, html, flags=re.DOTALL | re.IGNORECASE)
    
    ld_data = None
    for m in ld_matches:
        try:
            parsed = json.loads(m.strip())
            if isinstance(parsed, dict) and parsed.get("@type") == "JobPosting":
                ld_data = parsed
                break
            elif isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        ld_data = item
                        break
        except Exception:
            continue
    t_reg = (time.time() - t_reg_start) * 1000
    print(f"    + [Regex] Tìm thấy Schema JobPosting trong: {t_reg:.2f} ms")

    # -------------------------------------------------------------
    # [CẢI TIẾN 2]: Dùng SOUPSTRAINER chỉ định đọc đúng DIV thông tin chung
    # Bỏ qua 95% DOM còn lại (header, footer, ads, sidebar...)
    # -------------------------------------------------------------
    t_strain_start = time.time()
    # Bộ lọc Strainer: Chỉ giữ lại các khối thông tin chung của việc làm
    general_strainer = SoupStrainer("div", class_=lambda c: c and any(k in c for k in [
        "box-job-information-general-info", 
        "box-job-information-detail-item",
        "job-detail__box-header"
    ]))
    soup = BeautifulSoup(html, "lxml", parse_only=general_strainer)
    t_strain = (time.time() - t_strain_start) * 1000
    print(f"    + [SoupStrainer + lxml] Phân tích khối DOM mục tiêu trong: {t_strain:.2f} ms")

    # Bóc các trường thông tin trong khối được lọc
    dom_data = {}
    
    # 1. Các mục Cấp bậc, Học vấn, Số lượng tuyển, Hình thức làm việc
    for it in soup.select(".box-job-information-general-info-list__item"):
        title_el = it.select_one(".box-job-information-general-info-list__item--content-title")
        desc_el = it.select_one(".box-job-information-general-info-list__item--content-desc")
        if title_el and desc_el:
            dom_data[title_el.get_text(strip=True)] = desc_el.get_text(strip=True)

    # 2. Quy mô công ty & Thời gian làm việc
    for item in soup.select(".box-job-information-detail-item, .box-job-information-general-info"):
        text = item.get_text(separator=" | ", strip=True)
        if "Thời gian làm việc" in text and "working_hours" not in dom_data:
            m = re.search(r"Thời gian làm việc\s*\|\s*([^|]+)", text)
            if m: dom_data["working_hours"] = m.group(1).strip()
        if "Quy mô:" in text and "company_scale" not in dom_data:
            m = re.search(r"Quy mô:\s*\|\s*([^|]+)", text)
            if m: dom_data["company_scale"] = m.group(1).strip()

    # 3. Hạn nộp hồ sơ (nếu có trong text)
    m_dl = re.search(r"Hạn ứng tuyển:\s*([0-9/]+)", html)
    if m_dl:
        dom_data["deadline"] = m_dl.group(1).strip()

    # -------------------------------------------------------------
    # TỔNG HỢP DỮ LIỆU ĐẦY ĐỦ (JSON-LD + DOM)
    # -------------------------------------------------------------
    return {
        "url": job_url,
        "title": ld_data.get("title") if ld_data else None,
        "company": {
            "name": ld_data.get("hiringOrganization", {}).get("name") if ld_data else None,
            "profile_url": ld_data.get("hiringOrganization", {}).get("sameAs") if ld_data else None,
            "logo": ld_data.get("hiringOrganization", {}).get("logo") if ld_data else None,
            "scale": dom_data.get("company_scale")
        },
        "salary": ld_data.get("baseSalary") if ld_data else None,
        "location": ld_data.get("jobLocation", {}).get("address") if ld_data else None,
        "requirements": {
            "experienceMonths": ld_data.get("experienceRequirements", {}).get("monthsOfExperience") if ld_data else None,
            "education": dom_data.get("Học vấn"),
            "level": dom_data.get("Cấp bậc"),
            "working_type": dom_data.get("Hình thức làm việc") or (ld_data.get("employmentType") if ld_data else None),
            "working_hours": dom_data.get("working_hours"),
            "job_openings": ld_data.get("totalJobOpenings") or dom_data.get("Số lượng tuyển")
        },
        "dates": {
            "datePosted": ld_data.get("datePosted") if ld_data else None,
            "validThrough": ld_data.get("validThrough") if ld_data else None,
            "deadline_display": dom_data.get("deadline")
        },
        "industry": ld_data.get("industry") if ld_data else None,
        "description_preview": (BeautifulSoup(ld_data.get("description", ""), "lxml").get_text(strip=True)[:250] + "...") if ld_data and ld_data.get("description") else None,
        "full_ld_json": ld_data  # Giữ trọn vẹn 100% trường dữ liệu thô của Schema JSON-LD
    }

# ==============================================================================
# 4. CHẠY THỰC NGHIỆM KIỂM THỬ
# ==============================================================================
if __name__ == "__main__":
    session = create_crawler_session()
    
    # 1. Tìm kiếm danh sách jobs
    jobs = search_jobs(session, keyword="software-engineer", page=1)
    
    if jobs:
        print(f"\n==================================================================")
        print(f"[Thực nghiệm] Bắt đầu cào mẫu 2 công việc bằng engine mới...")
        print(f"==================================================================")
        
        sample_results = []
        for j in jobs[:2]:
            job_info = crawl_job_detail(session, j["url"])
            if job_info:
                sample_results.append(job_info)
            time.sleep(1) # Delay lịch sự

        output_path = "/home/lmaosama/Testing/topcv_test_output.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sample_results, f, ensure_ascii=False, indent=2)

        print(f"\n[✔] KIỂM THỬ THÀNH CÔNG RỰC RỠ!")
        print(f"[✔] Dữ liệu mẫu đã được ghi vào: {output_path}")
        print("\nXem mẫu dữ liệu đầu ra:\n")
        print(json.dumps(sample_results, ensure_ascii=False, indent=2))
