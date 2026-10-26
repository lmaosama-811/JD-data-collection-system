import json
# pyrefly: ignore[missing-import]
from bs4 import BeautifulSoup
# pyrefly: ignore[missing-import]
from curl_cffi import requests
import re

from .crawler_base import CrawlerBase, RAW_DATA_ROOT
# pyrefly: ignore[missing-import]
from backend.config.log_config import get_logger

logger = get_logger(__name__)


class VietnamWorksCrawler(CrawlerBase):
    file_path = RAW_DATA_ROOT / "vietnamworks"
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
    DELAY_PER_REQUESTS = 3.0

    def __init__(self, impersonate: str = "chrome124"):
        self.impersonate = impersonate
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Khởi tạo phiên curl_cffi giả lập Chrome 124"""
        session = requests.Session(impersonate=self.impersonate)
        session.headers.update(self.DEFAULT_HEADERS)
        return session

    def search_jobs(
        self,
        query: str = "software", 
        page: int = 1,
        hits_per_page: int = 50,
        filter_tech_only: bool = True,
        city_ids: str = None  # Ví dụ "24" (Hà Nội), "29" (TP.HCM), hoặc "24,29"
    ):
        """
        Gọi Search Listing API dạng POST.
        - filter_tech_only: Tự động gắn bộ lọc ngành IT Software/SaaS, IT System, Telecom.
        - hits_per_page: Lấy tối đa 50 việc làm mỗi request để tối ưu tốc độ.
        - page: Bắt đầu từ 1 (API nội bộ 0-indexed, được quy đổi bên dưới).
        """
        filters = []
    
        # 1. Áp dụng bộ lọc chỉ lấy ngành Tech
        if filter_tech_only:
            filters.append({
                "field": "industriesV3.industryV3Id",
                "value": self.TECH_INDUSTRY_IDS
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
            "page": page - 1,
            "retrieveFields": [
                "jobId", "jobTitle", "jobUrl", "companyId", "companyName", "companyLogo", 
                "companySize", "prettySalary", "isSalaryVisible", "salaryMin", "salaryMax", 
                "skills", "benefits", "workingLocations", "yearsOfExperience", "jobLevelVI", 
                "onlineOnText", "onlineOn", "expiredOn", "jobDescription", "jobRequirement"
            ]
        }

        raw = self._request("POST", self.SEARCH_API_URL, "VietnamWorks search", json=payload)
        result = self._extract_search(raw)
        logger.info("VietnamWorks search: query='%s', page=%d, %d job", query, page, len(result["items"]))
        return result

    def crawl_job_detail(self, job_url: str = None, job_id: str = None):
        """
        Gọi Tracking / Job-Info API để lấy toàn bộ Job Description, Requirements không bị cắt bớt.
        """
        if not job_id and job_url:
            m = re.search(r"-(\d+)-jv", job_url) or re.search(r"(\d+)", job_url.split("?")[0])
            job_id = m.group(1) if m else None
        if not job_id:
            raise ValueError("VietnamWorksCrawler.crawl_job_detail requires job_id or a valid job_url")
        url = f"{self.DETAIL_API_URL}?jobId={job_id}"
        raw = self._request("GET", url, "VietnamWorks detail")
        return self._extract_detail(raw)

    def _extract_search(self, raw: str) -> dict:
        """
        Nguồn JSON: giữ nguyên toàn bộ nội dung. Chỉ chuẩn hóa về dạng {"meta", "items"}:
        - items: danh sách job (`data`)
        - meta: các khóa còn lại của response (meta, facets, ...)
        """
        payload = json.loads(raw)
        return {
            "meta": {k: v for k, v in payload.items() if k != "data"},
            "items": payload.get("data") or [],
        }

    def _extract_detail(self, raw: str) -> dict:
        """Nguồn JSON: giữ nguyên toàn bộ response (status, message, data)."""
        return json.loads(raw)

    def merge_job_data(self, search_item: dict, detail_item: dict) -> dict:
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

    def get_job_refs(self, search_result: dict) -> list[dict]:
        """Từ kết quả search, trích job_id + job_url."""
        refs = []
        for item in search_result.get("items", []):
            job_id = item.get("jobId")
            if job_id is not None:
                refs.append({"job_id": str(job_id), "job_url": item.get("jobUrl")})
        return refs

vietnamworks_crawler = VietnamWorksCrawler()