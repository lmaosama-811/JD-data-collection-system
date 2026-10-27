import re
from typing import Dict, Optional
# pyrefly: ignore[missing-import]
from bs4 import BeautifulSoup
# pyrefly: ignore[missing-import]
from curl_cffi import requests
from .crawler_base import CrawlerBase, RAW_DATA_ROOT
# pyrefly: ignore[missing-import]
from backend.config.log_config import get_logger

logger = get_logger(__name__)


class LinkedInCrawler(CrawlerBase):
    file_path = RAW_DATA_ROOT / "linkedin"
    BASE_URL = "https://www.linkedin.com"
    SEARCH_API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    DETAIL_API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    DEFAULT_HEADERS = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "accept-language": "en-US,en;q=0.9,vi;q=0.8",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    
    DELAY_PER_REQUESTS = 5.0
    PAGE_SIZE = 10  # số job mỗi trang (offset `start` = (page - 1) * PAGE_SIZE)

    def __init__(
        self,
        cookies: Optional[Dict[str, str]] = None,
        impersonate: str = "chrome124",
        timeout: int = 40
    ):
        self.impersonate = impersonate
        self.timeout = timeout
        self.cookies = cookies or {}
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        s = requests.Session(impersonate=self.impersonate)
        if self.cookies:
            for k, v in self.cookies.items():
                s.cookies.set(k, v, domain=".linkedin.com")
        return s

    def search_jobs(
        self,
        page: int = 1,
        keywords: str = "Python",
        location: str = "Vietnam"
    ) -> dict:
        params = {
            "keywords": keywords,
            "location": location,
            "start": (page - 1) * self.PAGE_SIZE
        }

        raw = self._request("GET", self.SEARCH_API_URL, "LinkedIn search",
                            params=params, headers=self.DEFAULT_HEADERS, timeout=self.timeout)
        result = self._extract_search(raw)
        logger.info("LinkedIn search: keywords='%s', location='%s', page=%d, %d job", keywords, location, page, len(result["items"]))
        return result

    def crawl_job_detail(self, job_url: str = None, job_id: str = None) -> dict:
        if not job_id and job_url:
            m = re.search(r"(\d{6,})", job_url)
            job_id = m.group(1) if m else None
        if not job_id:
            raise ValueError("LinkedInCrawler.crawl_job_detail requires job_id or a valid job_url")
        url = self.DETAIL_API_URL.format(job_id=job_id)
        raw = self._request("GET", url, "LinkedIn detail", headers=self.DEFAULT_HEADERS, timeout=self.timeout)
        return self._extract_detail(raw)

    def _parse_search_card(self, card) -> dict:
        t = self._text
        urn = card.get("data-entity-urn") or ""
        m = re.search(r"jobPosting:(\d+)", urn)
        link = card.select_one("a.base-card__full-link")
        company_a = card.select_one(".base-search-card__subtitle a")
        logo = card.select_one("img[data-delayed-url]")
        time_el = card.select_one("time")
        benefit = card.select_one(".job-posting-benefits__text")
        return {
            "job_id": m.group(1) if m else None,
            "job_url": self._clean_url(link.get("href")) if link else None,
            "title": t(card.select_one(".base-search-card__title")),
            "company": {
                "name": t(card.select_one(".base-search-card__subtitle")),
                "url": self._clean_url(company_a.get("href")) if company_a else None,
                "logo": logo.get("data-delayed-url") if logo else None,
            },
            "location": t(card.select_one(".job-search-card__location")),
            "posted_date": time_el.get("datetime") if time_el else None,
            "posted_text": t(time_el),
            "is_new": bool(card.select_one(".job-search-card__listdate--new")),
            "benefit_badge": t(benefit),
        }

    def _extract_search(self, raw: str) -> dict:
        soup = BeautifulSoup(raw, "lxml")
        items = [self._parse_search_card(c) for c in soup.select("div.base-card")]
        return {"meta": {}, "items": items}

    def _extract_detail(self, raw: str) -> dict:
        soup = BeautifulSoup(raw, "lxml")
        t = self._text

        desc_el = soup.select_one(".show-more-less-html__markup")
        if desc_el is None:
            raise ValueError("LinkedIn detail: không tìm thấy phần mô tả (trang có thể bị chặn/đổi cấu trúc)")

        title_link = soup.select_one("a.topcard__link")
        company_a = soup.select_one(".topcard__org-name-link")
        logo = soup.select_one(".top-card-layout img.artdeco-entity-image")
        m = re.search(r'id="decoratedJobPostingId"[^>]*>\s*<!--\s*"(\d+)"\s*-->', raw)

        return {
            "job_id": m.group(1) if m else None,
            "job_url": self._clean_url(title_link.get("href")) if title_link else None,
            "title": t(soup.select_one(".top-card-layout__title")),
            "company": {
                "name": t(company_a) or t(soup.select_one(".topcard__flavor")),
                "url": self._clean_url(company_a.get("href")) if company_a else None,
                "logo": (logo.get("data-delayed-url") or logo.get("src")) if logo else None,
            },
            "location": t(soup.select_one(".topcard__flavor--bullet")),
            "posted_text": t(soup.select_one(".posted-time-ago__text")),
            "applicants_text": t(soup.select_one(".num-applicants__caption")),
            "criteria": [
                {
                    "label": t(it.select_one(".description__job-criteria-subheader")),
                    "value": t(it.select_one(".description__job-criteria-text")),
                }
                for it in soup.select("li.description__job-criteria-item")
            ],
            "description_html": "".join(str(c) for c in desc_el.contents).strip(),
        }

    def get_job_refs(self, search_result: dict) -> list[dict]:
        """Từ kết quả search, trích job_id + job_url."""
        refs, seen = [], set()
        for item in search_result.get("items", []):
            job_id = item.get("job_id")
            if job_id and job_id not in seen:
                seen.add(job_id)
                refs.append({"job_id": job_id, "job_url": item.get("job_url")})
        return refs


linkedin_crawler = LinkedInCrawler()