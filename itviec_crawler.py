import json
import re
import time
from bs4 import BeautifulSoup, SoupStrainer
from curl_cffi import requests

# ==============================================================================
# 1. CẤU HÌNH PHIÊN LÀM VIỆC VỚI ITVIEC
# ==============================================================================
BASE_URL = "https://itviec.com"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def create_itviec_session() -> requests.Session:
    """
    Khởi tạo Session curl_cffi giả lập Chrome 124.
    ITviec sử dụng Cloudflare, nên việc giả lập TLS fingerprint là bắt buộc để tránh bị chặn 403.
    """
    session = requests.Session(impersonate="chrome124")
    session.headers.update({
        "authority": "itviec.com",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "user-agent": DEFAULT_USER_AGENT
    })
    return session

# ==============================================================================
# 2. BƯỚC 1 & 2: FETCH DANH SÁCH VIỆC LÀM & BÓC TÁCH LINK JOB TỪ DOM
# ==============================================================================
def fetch_job_urls(session: requests.Session, page: int = 1):
    """
    Tải trang danh sách job của ITviec: https://itviec.com/it-jobs?page=x
    Dùng SoupStrainer lọc riêng các thẻ .job-card để bóc tách link việc làm.
    """
    url = f"{BASE_URL}/it-jobs?page={page}"
    print(f"\n==================================================================")
    print(f"[Bước 1] Fetch HTML danh sách việc làm: {url}")
    print(f"==================================================================")

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "referer": BASE_URL,
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin"
    }

    t0 = time.time()
    resp = session.get(url, headers=headers)
    dl_time = time.time() - t0

    if resp.status_code != 200:
        print(f"[!] Lỗi khi truy cập danh sách việc làm. HTTP: {resp.status_code}")
        return []

    print(f"[✔] Tải trang danh sách thành công trong {dl_time:.2f}s ({len(resp.text)} bytes)")

    print(f"\n[Bước 2] Bóc tách link chi tiết từng công việc từ các thẻ .job-card...")
    # Tối ưu hóa: Dùng SoupStrainer chỉ parse các thẻ div.job-card
    card_strainer = SoupStrainer("div", class_=lambda c: c and "job-card" in c)
    soup = BeautifulSoup(resp.text, "lxml", parse_only=card_strainer)

    job_cards = soup.select(".job-card")
    job_list = []

    for card in job_cards:
        # Link chính của job nằm ở thẻ <a> đầu tiên dẫn tới /it-jobs/<slug>
        title_link = None
        for a in card.find_all("a", href=True):
            href = a["href"]
            if "/it-jobs/" in href and not any(tag in href for tag in ["click_source=Skill", "click_source=Navigation"]):
                title_link = a
                break

        if title_link:
            title = title_link.get_text(strip=True)
            href = title_link["href"]
            # Chuẩn hóa URL tuyệt đối
            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            # Bỏ query params rác như ?lab_feature=preview_jd_page
            clean_url = full_url.split("?")[0]
            
            # Lấy tên công ty nếu có sẵn trên card
            company_el = card.select_one("a[href*='/companies/'].text-rich-grey") or card.select_one(".employer-name") or card.select_one("a[href*='/companies/']")
            company_name = company_el.get_text(strip=True) if company_el else None

            job_list.append({
                "title": title,
                "url": clean_url,
                "company_name": company_name
            })

    print(f"[✔] Trích xuất thành công {len(job_list)} việc làm từ trang {page}:")
    for idx, j in enumerate(job_list[:5], 1):
        print(f"  {idx}. {j['title']} ({j['company_name']})")
        print(f"     URL: {j['url']}")

    return job_list

# ==============================================================================
# 3. BƯỚC 3 & 4: CÀO TRANG CHI TIẾT JOB (LỌC 3 THẺ LD+JSON & PARSE DOM)
# ==============================================================================
def crawl_itviec_job_detail(session: requests.Session, job_url: str):
    """
    Truy cập link chi tiết job:
    1. Dùng Regex lọc toàn bộ các thẻ <script type='application/ld+json'> (thường có 3 thẻ).
    2. Lọc chính xác thẻ có "@type": "JobPosting".
    3. Dùng SoupStrainer để chỉ bóc tách các trường còn thiếu từ DOM.
    """
    print(f"\n--> Đang cào dữ liệu chi tiết: {job_url}")
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "referer": f"{BASE_URL}/it-jobs",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin"
    }

    t0 = time.time()
    resp = session.get(job_url, headers=headers)
    dl_time = time.time() - t0

    if resp.status_code != 200:
        print(f"[!] Không thể truy cập job. Mã lỗi: {resp.status_code}")
        return None

    html = resp.text
    print(f"    + Tải trang xong: {len(html)} ký tự ({dl_time:.2f}s)")

    # --------------------------------------------------------------------------
    # [LỌC THẺ LD+JSON BẰNG REGEX]
    # ITviec thường nhúng 3 thẻ: JobPosting, BreadcrumbList, WebSite
    # --------------------------------------------------------------------------
    t_reg_start = time.time()
    pattern = r'<script[^>]*type=[\'\"]application/ld\+json[\'\"][^>]*>(.*?)</script>'
    matches = re.findall(pattern, html, flags=re.DOTALL | re.IGNORECASE)
    
    job_posting_data = None
    all_schemas = []

    for m in matches:
        try:
            parsed = json.loads(m.strip())
            schema_type = parsed.get("@type")
            all_schemas.append(schema_type)
            if schema_type == "JobPosting":
                job_posting_data = parsed
        except Exception:
            continue

    t_reg = (time.time() - t_reg_start) * 1000
    print(f"    + [Regex] Tìm thấy {len(matches)} thẻ ld+json (gồm: {all_schemas}) trong: {t_reg:.2f} ms")

    # --------------------------------------------------------------------------
    # [BÓC TÁCH DOM BẰNG SOUPSTRAINER]
    # Chỉ định parser đọc đúng các vùng chứa thông tin làm việc và thông tin công ty
    # --------------------------------------------------------------------------
    t_strain_start = time.time()
    info_strainer = SoupStrainer("div", class_=lambda c: c and any(k in c for k in [
        "job-header-info",
        "job-show-info",
        "employer-overview",
        "job-details"
    ]))
    soup = BeautifulSoup(html, "lxml", parse_only=info_strainer)
    t_strain = (time.time() - t_strain_start) * 1000
    print(f"    + [SoupStrainer + lxml] Phân tích khối DOM mục tiêu trong: {t_strain:.2f} ms")

    dom_data = {}

    # 1. Thông tin chế độ làm việc trong .job-show-info (At office / Hybrid / Remote, Địa chỉ, Domain, Expertise)
    show_info = soup.select_one(".job-show-info")
    if show_info:
        info_text = show_info.get_text(separator=" | ", strip=True)
        # Bóc hình thức làm việc
        for wm in ["At office", "Hybrid", "Remote"]:
            if wm in info_text:
                dom_data["work_model"] = wm
                break
        
        # Bóc Job Expertise & Domain
        if "Job Expertise:" in info_text:
            m = re.search(r"Job Expertise:\s*\|\s*([^|]+)", info_text)
            if m: dom_data["job_expertise"] = m.group(1).strip()
            
        if "Job Domain:" in info_text:
            m = re.search(r"Job Domain:\s*\|\s*([^|]+)", info_text)
            if m: dom_data["job_domain"] = m.group(1).strip()

        if "Posted" in info_text:
            m = re.search(r"Posted\s*\|\s*([^|]+)", info_text)
            if m: dom_data["posted_relative"] = m.group(1).strip()

    # 2. Bóc thông tin hiển thị mức lương trên giao diện (Sign in to view salary hay Lương cụ thể)
    salary_el = soup.select_one(".job-header-info .salary, .job-show-header .salary, .sign-in-view-salary")
    if salary_el:
        dom_data["ui_salary_display"] = salary_el.get_text(strip=True)

    # 3. Bóc thông tin công ty: Company type, Industry, Company size, Country, Working days, Overtime policy
    for row in soup.find_all("div", class_=lambda c: c and "row" in c and "ipy-2" in c):
        txt = row.get_text(separator=" | ", strip=True)
        for label in ["Company type", "Company industry", "Company size", "Country", "Working days", "Overtime policy"]:
            if label in txt:
                parts = txt.split("|")
                for i, p in enumerate(parts):
                    if label in p and i + 1 < len(parts):
                        dom_data[label.lower().replace(" ", "_")] = parts[i + 1].strip()

    # --------------------------------------------------------------------------
    # HỢP NHẤT DỮ LIỆU ĐẦY ĐỦ
    # --------------------------------------------------------------------------
    result = {
        "url": job_url,
        "title": job_posting_data.get("title") if job_posting_data else None,
        "company": {
            "name": job_posting_data.get("hiringOrganization", {}).get("name") if job_posting_data else None,
            "logo": job_posting_data.get("hiringOrganization", {}).get("logo") if job_posting_data else None,
            "type": dom_data.get("company_type"),
            "industry": dom_data.get("company_industry"),
            "size": dom_data.get("company_size"),
            "country": dom_data.get("country"),
            "working_days": dom_data.get("working_days"),
            "overtime_policy": dom_data.get("overtime_policy")
        },
        "salary_info": {
            "schema_salary": job_posting_data.get("baseSalary") if job_posting_data else None,
            "ui_display_salary": dom_data.get("ui_salary_display")
        },
        "job_details": {
            "employment_type": job_posting_data.get("employmentType") if job_posting_data else None,
            "work_model": dom_data.get("work_model"),
            "experience_months": job_posting_data.get("experienceRequirements", {}).get("monthsOfExperience") if job_posting_data else None,
            "skills_required": job_posting_data.get("skills") if job_posting_data else None,
            "job_expertise": dom_data.get("job_expertise"),
            "job_domain": dom_data.get("job_domain"),
            "locations": job_posting_data.get("jobLocation") if job_posting_data else None,
            "date_posted": job_posting_data.get("datePosted") if job_posting_data else None,
            "valid_through": job_posting_data.get("validThrough") if job_posting_data else None,
            "posted_relative": dom_data.get("posted_relative"),
            "apply_url": job_posting_data.get("potentialAction", {}).get("target") if job_posting_data else None
        },
        "description_preview": (BeautifulSoup(job_posting_data.get("description", ""), "lxml").get_text(strip=True)[:250] + "...") if job_posting_data and job_posting_data.get("description") else None,
        "raw_job_posting_schema": job_posting_data
    }
    return result

# ==============================================================================
# 4. CHẠY KIỂM THỬ THỰC TẾ
# ==============================================================================
if __name__ == "__main__":
    session = create_itviec_session()

    # Bước 1 & 2: Lấy link 20 jobs từ page 1
    jobs = fetch_job_urls(session, page=1)

    if jobs:
        print(f"\n==================================================================")
        print(f"[Thực nghiệm] Bắt đầu cào mẫu 2 công việc đầu tiên trên ITviec...")
        print(f"==================================================================")

        sample_results = []
        for j in jobs[:2]:
            job_info = crawl_itviec_job_detail(session, j["url"])
            if job_info:
                sample_results.append(job_info)
            time.sleep(1) # Giãn cách an toàn 1 giây giữa các request

        output_path = "/home/lmaosama/Testing/itviec_test_output.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sample_results, f, ensure_ascii=False, indent=2)

        print(f"\n[✔] KIỂM THỬ THÀNH CÔNG RỰC RỠ!")
        print(f"[✔] Dữ liệu mẫu đã được ghi vào file: {output_path}")
        print("\nXem mẫu dữ liệu đầu ra:\n")
        print(json.dumps(sample_results, ensure_ascii=False, indent=2))
