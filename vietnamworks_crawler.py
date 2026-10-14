import json
import time
from bs4 import BeautifulSoup
from curl_cffi import requests

# ==============================================================================
# 1. CẤU HÌNH API ENDPOINTS & HEADERS
# ==============================================================================
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

# Các mã ngành Công nghệ thông tin trên VietnamWorks:
# 25: IT Software / SaaS (Phần mềm)
# 26: IT System & Devices (Hệ thống & Thiết bị CNTT)
# 27: Telecommunications (Viễn thông)
TECH_INDUSTRY_IDS = "25,26,27"

def create_vnw_session() -> requests.Session:
    """Khởi tạo phiên curl_cffi giả lập Chrome 124"""
    session = requests.Session(impersonate="chrome124")
    session.headers.update(DEFAULT_HEADERS)
    return session

# ==============================================================================
# 2. BƯỚC 1 & 2: GỌI SEARCH LISTING API VỚI BỘ LỌC TECH & TỪ KHÓA
# ==============================================================================
def search_jobs(
    session: requests.Session, 
    query: str = "software", 
    page: int = 0, 
    hits_per_page: int = 50,
    filter_tech_only: bool = True,
    city_ids: str = None  # Ví dụ "24" (Hà Nội), "29" (TP.HCM), hoặc "24,29"
):
    """
    Gọi Search Listing API dạng POST.
    - filter_tech_only: Tự động gắn bộ lọc ngành IT Software/SaaS, IT System, Telecom.
    - hits_per_page: Lấy tối đa 50 việc làm mỗi request để tối ưu tốc độ.
    - page: Bắt đầu từ 0 (0-indexed).
    """
    filters = []
    
    # 1. Áp dụng bộ lọc chỉ lấy ngành Tech
    if filter_tech_only:
        filters.append({
            "field": "industriesV3.industryV3Id",
            "value": TECH_INDUSTRY_IDS
        })
        
    # 2. Áp dụng bộ lọc địa điểm (nếu có)
    if city_ids:
        filters.append({
            "field": "workingLocations.cityId",
            "value": str(city_ids)
        })

    payload = {
        "userId": 0,
        "query": query,
        "filter": filters,
        "ranges": [],
        "order": [],
        "hitsPerPage": hits_per_page,
        "page": page,
        "retrieveFields": [
            "jobId", "jobTitle", "jobUrl", "companyId", "companyName", "companyLogo", 
            "companySize", "prettySalary", "isSalaryVisible", "salaryMin", "salaryMax", 
            "skills", "benefits", "workingLocations", "yearsOfExperience", "jobLevelVI", 
            "onlineOnText", "onlineOn", "expiredOn", "jobDescription", "jobRequirement"
        ]
    }

    print(f"\n==================================================================")
    print(f"[Bước 1] Gửi Search API: Keyword='{query}' | Tech Filter={filter_tech_only} | Page={page + 1} ({hits_per_page} jobs/page)")
    print(f"==================================================================")

    t0 = time.time()
    resp = session.post(SEARCH_API_URL, json=payload)
    latency = time.time() - t0

    if resp.status_code != 200:
        print(f"[!] Lỗi kết nối Search API. HTTP Status: {resp.status_code}")
        print("Chi tiết:", resp.text[:300])
        return []

    data = resp.json()
    meta = data.get("meta", {})
    job_items = data.get("data", [])
    
    total_hits = meta.get("nbHits", 0)
    total_pages = meta.get("nbPages", 0)

    print(f"[✔] Nhận phản hồi thành công trong {latency:.2f}s!")
    print(f"[✔] Tổng số việc làm TECH phù hợp trên hệ thống: {total_hits} (Tổng cộng: {total_pages} trang)")
    print(f"[✔] Đã tải danh sách {len(job_items)} việc làm trong trang này.")

    print(f"\n[Bước 2] Trích xuất danh sách 5 việc làm đầu tiên:")
    for idx, j in enumerate(job_items[:5], 1):
        job_id = j.get("jobId")
        title = j.get("jobTitle")
        company = j.get("companyName")
        salary = j.get("prettySalary")
        print(f"  {idx}. [ID: {job_id}] {title}")
        print(f"     Công ty: {company} | Lương: {salary}")

    return job_items

# ==============================================================================
# 3. BƯỚC 3 & 4: GỌI DETAIL API QUA JOB_ID ĐỂ LẤY FULL NỘI DUNG & HỢP NHẤT
# ==============================================================================
def get_job_detail(session: requests.Session, job_id: int):
    """
    Gọi Tracking / Job-Info API để lấy toàn bộ Job Description, Requirements không bị cắt bớt.
    """
    url = f"{DETAIL_API_URL}?jobId={job_id}"
    print(f"\n--> Gọi Detail API: {url}")
    
    t0 = time.time()
    resp = session.get(url)
    latency = time.time() - t0

    if resp.status_code != 200:
        print(f"[!] Lỗi khi lấy chi tiết job ID {job_id}. Status: {resp.status_code}")
        return None

    detail_data = resp.json().get("data", {})
    print(f"    + Nhận JSON chi tiết trong: {latency*1000:.1f}ms")
    return detail_data

def merge_job_data(search_item: dict, detail_item: dict) -> dict:
    """
    Hợp nhất dữ liệu: Search API (Kỹ năng, phúc lợi, địa chỉ) + Detail API (Full HTML mô tả, yêu cầu).
    """
    full_desc_html = detail_item.get("job_description") or search_item.get("jobDescription", "")
    full_req_html = detail_item.get("job_requirement") or search_item.get("jobRequirement", "")

    desc_clean = BeautifulSoup(full_desc_html, "lxml").get_text(separator=" ", strip=True) if full_desc_html else ""
    req_clean = BeautifulSoup(full_req_html, "lxml").get_text(separator=" ", strip=True) if full_req_html else ""

    return {
        "job_id": search_item.get("jobId"),
        "job_title": search_item.get("jobTitle"),
        "job_url": search_item.get("jobUrl"),
        "company": {
            "id": search_item.get("companyId"),
            "name": search_item.get("companyName"),
            "logo": search_item.get("companyLogo"),
            "industry": detail_item.get("company_industry"),
            "size": search_item.get("companySize")
        },
        "salary": {
            "pretty_salary": search_item.get("prettySalary"),
            "is_salary_visible": search_item.get("isSalaryVisible"),
            "salary_min": search_item.get("salaryMin"),
            "salary_max": search_item.get("salaryMax"),
            "salary_range_detail": detail_item.get("salary_range")
        },
        "requirements": {
            "years_of_experience": search_item.get("yearsOfExperience") or detail_item.get("number_of_years_of_experience_required"),
            "job_level": search_item.get("jobLevelVI") or detail_item.get("job_level_name"),
            "skills": [s.get("skillName") for s in search_item.get("skills", [])],
            "full_requirement_html": full_req_html,
            "requirement_preview": (req_clean[:250] + "...") if req_clean else None
        },
        "description": {
            "full_description_html": full_desc_html,
            "description_preview": (desc_clean[:250] + "...") if desc_clean else None
        },
        "benefits": [
            {
                "name": b.get("benefitNameVI") or b.get("benefitName"),
                "value": b.get("benefitValue")
            }
            for b in search_item.get("benefits", [])
        ],
        "locations": [
            {
                "city": loc.get("cityNameVI") or loc.get("cityName"),
                "address": loc.get("address")
            }
            for loc in search_item.get("workingLocations", [])
        ],
        "dates": {
            "posted_text": search_item.get("onlineOnText"),
            "online_on": search_item.get("onlineOn"),
            "expired_date": detail_item.get("job_expired_date") or search_item.get("expiredOn")
        }
    }

# ==============================================================================
# 4. CHẠY THỰC NGHIỆM KIỂM THỬ
# ==============================================================================
if __name__ == "__main__":
    session = create_vnw_session()

    # 1. Gọi Search Listing API với bộ lọc TECH và lấy 50 jobs/trang
    job_items = search_jobs(
        session, 
        query="software",           # Từ khóa tìm kiếm (hoặc "" để lấy tất cả)
        page=0,                     # Trang đầu tiên (index 0)
        hits_per_page=50,           # 50 jobs mỗi trang
        filter_tech_only=True       # Chỉ lấy ngành IT Software, System, Telecom
    )

    if job_items:
        print(f"\n==================================================================")
        print(f"[Thực nghiệm] Bắt đầu cào full chi tiết 2 việc làm TECH đầu tiên...")
        print(f"==================================================================")

        sample_results = []
        for item in job_items[:2]:
            job_id = item.get("jobId")
            detail = get_job_detail(session, job_id)
            if detail:
                merged = merge_job_data(item, detail)
                sample_results.append(merged)
            time.sleep(0.5) # Giãn cách an toàn

        output_path = "/home/lmaosama/Testing/vietnamworks_test_output.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sample_results, f, ensure_ascii=False, indent=2)

        print(f"\n[✔] KIỂM THỬ THÀNH CÔNG RỰC RỠ!")
        print(f"[✔] Dữ liệu mẫu 2 việc làm TECH đã được ghi vào file: {output_path}")
        print("\nXem mẫu dữ liệu đầu ra:\n")
        print(json.dumps(sample_results, ensure_ascii=False, indent=2))
