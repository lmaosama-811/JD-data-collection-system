import json
import logging
from typing import Any, Dict, List, Optional, Tuple
# pyrefly: ignore[missing-import]
from bs4 import BeautifulSoup
import re
# pyrefly: ignore[missing-import]
from curl_cffi import requests

from .crawler_base import CrawlerBase, RAW_DATA_ROOT
# pyrefly: ignore[missing-import]
from backend.config.log_config import get_logger


logger = get_logger(__name__)


class NodeFlairCrawler(CrawlerBase):
    file_path = RAW_DATA_ROOT / "nodeflair"
    BASE_URL = "https://nodeflair.com"
    SEARCH_API_URL = "https://nodeflair.com/api/v2/jobs"
    DETAIL_API_URL = "https://nodeflair.com/api/v2/jobs/{job_id}"

    # Required headers to pass Cloudflare WAF on NodeFlair
    HEADERS_API = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "origin": "https://nodeflair.com",
        "referer": "https://nodeflair.com/jobs",
    }
    
    DELAY_PER_REQUESTS = 3.0

    def __init__(self, impersonate: str = "chrome124", timeout: int = 120):
        self.impersonate = impersonate
        self.timeout = timeout
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        return requests.Session(impersonate=self.impersonate)

    def search_jobs(
        self,
        query: str = "software",
        page: int = 1,
        sort_by: str = "relevant",
        country: str = "Vietnam"
    ) -> dict:
        """
        Fetch structured job items from Search Listing API.
        """
        params = {
            "query": query,
            "page": page,
            "sort_by": sort_by,
            "countries[]": country
        }

        raw = self._request("GET", self.SEARCH_API_URL, "NodeFlair search",
                            params=params, headers=self.HEADERS_API, timeout=self.timeout)
        result = self._extract_search(raw)
        logger.info("NodeFlair search: query='%s', page=%d, country='%s', %d job (tổng %s)",
                    query, page, country, len(result["items"]), result["meta"].get("total_listings_count"))
        return result

    def crawl_job_detail(self, job_url: str = None, job_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Direct Detail REST API call.
        Returns job details if HTTP 200, None if HTTP 404 or any other error.
        Nhận job_id, hoặc job_url (job_id được trích từ số trong URL).
        """
        if not job_id and job_url:
            m = re.search(r"/jobs/(\d+)", job_url) or re.search(r"(\d+)", job_url.split("?")[0])
            job_id = m.group(1) if m else None
        if not job_id:
            raise ValueError("NodeFlairCrawler.crawl_job_detail requires job_id or a valid job_url")
        api_url = self.DETAIL_API_URL.format(job_id=job_id)
        raw = self._request("GET", api_url, "NodeFlair detail", headers=self.HEADERS_API, timeout=self.timeout)
        return self._extract_detail(raw)

    def _extract_search(self, raw: str) -> dict:
        """
        Nguồn JSON: giữ nguyên toàn bộ nội dung. Chỉ chuẩn hóa về dạng {"meta", "items"}:
        - items: danh sách job (`job_listings`)
        - meta: các khóa còn lại (total_listings_count, has_job_alert, ...)
        """
        payload = json.loads(raw)
        return {
            "meta": {k: v for k, v in payload.items() if k != "job_listings"},
            "items": payload.get("job_listings") or [],
        }

    def _extract_detail(self, raw: str) -> dict:
        """Nguồn JSON: giữ nguyên toàn bộ response (job, company, salaries)."""
        return json.loads(raw)

    def get_job_refs(self, search_result: dict) -> list[dict]:
        """Từ kết quả search, trích job_id + job_url."""
        refs = []
        for item in search_result.get("items", []):
            job_id = item.get("id")
            job_path = (item.get("job_path") or "").split("?")[0]
            if job_id is not None:
                refs.append({
                    "job_id": str(job_id),
                    "job_url": f"{self.BASE_URL}{job_path}" if job_path else None,
                })
        return refs

nodeflair_crawler = NodeFlairCrawler()