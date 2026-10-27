import json
import re
# pyrefly: ignore[missing-import]
from bs4 import BeautifulSoup
# pyrefly: ignore[missing-import]
from curl_cffi import requests

from .crawler_base import CrawlerBase, RAW_DATA_ROOT
# pyrefly: ignore[missing-import]
from backend.config.log_config import get_logger

logger = get_logger(__name__)


class ITViecCrawler(CrawlerBase):
    file_path = RAW_DATA_ROOT / "itviec"
    BASE_URL = "https://itviec.com"
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    DELAY_PER_REQUESTS = 3.0

    def __init__(self, impersonate: str = "chrome124"):
        self.impersonate = impersonate
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session(impersonate=self.impersonate)
        session.headers.update({
            "authority": "itviec.com",
            "accept-language": "en-US,en;q=0.9,vi;q=0.8",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "user-agent": self.DEFAULT_USER_AGENT
        })
        return session

    def search_jobs(self, page: int = 1) -> dict:
        url = f"{self.BASE_URL}/it-jobs?page={page}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "referer": self.BASE_URL,
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin"
        }

        raw = self._request("GET", url, "ITViec search", headers=headers)
        result = self._extract_search(raw)
        logger.info("ITViec search: page=%d, %d job", page, len(result["items"]))
        return result

    def crawl_job_detail(self, job_url: str = None, job_id: str = None) -> dict:
        if not job_url:
            raise ValueError("ITViecCrawler.crawl_job_detail requires job_url")
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "referer": f"{self.BASE_URL}/it-jobs",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin"
        }

        raw = self._request("GET", job_url, "ITViec detail", headers=headers)
        return self._extract_detail(raw)

    def _abs(self, href: str):
        if not href:
            return None
        return href if href.startswith("http") else f"{self.BASE_URL}{href}"

    def _parse_search_card(self, card) -> dict:
        t = self._text
        title_a = card.select_one("h3 a")
        company_logo_a = card.select_one("a.logo-employer-card")
        company_name_a = card.select_one("a.text-rich-grey[href*='/companies/']")
        logo_img = card.select_one("a.logo-employer-card img")
        salary_el = card.select_one(".salary")

        # 2 hàng thông tin dưới đường kẻ đứt: [expertise] và [work model, địa điểm]
        info_rows = card.select("div.imt-1")
        expertise_a = info_rows[0].select_one("a") if len(info_rows) > 0 else None
        info_texts = []
        if len(info_rows) > 1:
            info_texts = [t(d) for d in info_rows[1].find_all("div", recursive=False)
                          if t(d) and "dot-icon" not in d.get("class", [])]

        return {
            "job_slug": card.get("data-search--job-selection-job-slug-value"),
            "job_key": card.get("data-job-key"),
            "job_url": self._abs(self._clean_url(title_a.get("href"))) if title_a else None,
            "title": t(title_a),
            "labels": [t(l) for l in card.select(".ilabel") if t(l)],
            "posted_text": t(card.select_one("span.small-text")),
            "company": {
                "name": t(company_name_a),
                "full_name": company_logo_a.get("title") if company_logo_a else None,
                "url": self._abs(self._clean_url(company_logo_a.get("href"))) if company_logo_a else None,
                "logo": (logo_img.get("data-src") or logo_img.get("src")) if logo_img else None,
            },
            "salary_text": t(salary_el),
            "expertise": {"text": t(expertise_a), "href": expertise_a.get("href") if expertise_a else None},
            "info_texts": info_texts,
            "highlight_tags": [{"text": t(a), "href": a.get("href")} for a in card.select("div.d-flex.align-items-end a")],
            "reasons": [t(li) for li in card.select("li")],
            "skills": [{"text": t(a), "href": a.get("href")} for a in card.select("a.itag")],
        }

    def _extract_search(self, raw: str) -> dict:
        soup = BeautifulSoup(raw, "lxml")
        items = [self._parse_search_card(c) for c in soup.select("div.job-card")]
        pagination = soup.select_one(".pagination-search-jobs")
        return {
            "meta": {
                "total_text": self._text(soup.select_one(".headline-total-jobs")),
                "pagination_text": self._text(pagination),
            },
            "items": items,
        }

    def _extract_detail(self, raw: str) -> dict:
        soup = BeautifulSoup(raw, "lxml")
        t = self._text

        job_posting = None
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                parsed = json.loads(s.string or "")
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict) and parsed.get("@type") == "JobPosting":
                job_posting = parsed
                break
        if job_posting is None:
            raise ValueError("ITViec detail: không tìm thấy JSON-LD JobPosting (trang có thể bị chặn/đổi cấu trúc)")

        header_el = soup.select_one(".job-header-info")
        header = {
            "title": t(header_el.select_one("h1")) if header_el else "",
            "employer_name": t(header_el.select_one(".employer-name")) if header_el else "",
            "salary_text": t(header_el.select_one(".salary")) if header_el else "",
        }

        # show-info: các mục đầu (địa chỉ nhiều dòng, work model, Posted) + các hàng "Nhãn: giá trị"
        show_el = soup.select_one(".job-show-info")
        show_info = {"items": [], "rows": []}
        if show_el is not None:
            top = show_el.select_one(".imb-3 > div.d-flex.flex-column")
            if top is not None:
                for child in top.find_all("div", recursive=False):
                    maps_a = child.select_one("a[href*='google.com/maps']")
                    show_info["items"].append({"text": t(child), "maps_href": maps_a.get("href") if maps_a else None})
            for label_el in show_el.select("div.fw-600"):
                value_el = label_el.find_next_sibling("div")
                show_info["rows"].append({
                    "label": t(label_el),
                    "values": [{"text": t(v), "href": v.get("href")} for v in (value_el.select(".itag") if value_el else [])],
                })

        content_sections = []
        content_el = soup.select_one(".job-content")
        if content_el is not None:
            for p in content_el.select(":scope > .paragraph"):
                h2 = p.find("h2")
                content_sections.append({
                    "heading": t(h2),
                    "html": "".join(str(c) for c in p.contents if c is not h2).strip(),
                })

        employer_el = soup.select_one(".job-show-employer-info")
        company = None
        if employer_el is not None:
            name_a = employer_el.select_one("h3 a")
            logo_img = employer_el.select_one("img")
            details = []
            for row in employer_el.select(".row.ipy-2"):
                cols = row.find_all("div", recursive=False)
                if len(cols) >= 2:
                    details.append({"label": t(cols[0]), "value": t(cols[1])})
            rating_a = employer_el.select_one("a[href*='/review']")
            company = {
                "name": t(name_a) or t(employer_el.select_one("h3")),
                "url": self._abs(name_a.get("href")) if name_a else None,
                "logo": (logo_img.get("data-src") or logo_img.get("src")) if logo_img else None,
                "tagline": t(employer_el.select_one("p")),
                "rating": ({
                    "text": t(rating_a.select_one(".h4")),
                    "href": self._abs(self._clean_url(rating_a.get("href"))),
                } if rating_a is not None else None),
                "details": details,
            }

        m = re.search(r'<!--\s*Last updated:\s*"([^"]+)"\s*-->', raw)

        return {
            "job_posting": job_posting,
            "header": header,
            "show_info": show_info,
            "content_sections": content_sections,
            "company": company,
            "last_updated": m.group(1) if m else None,
        }

    def get_job_refs(self, search_result: dict) -> list[dict]:
        """Từ kết quả search, trích job_url (ITViec không có job_id riêng, id nằm cuối slug)."""
        refs, seen = [], set()
        for item in search_result.get("items", []):
            url = item.get("job_url")
            if url and url not in seen:
                seen.add(url)
                refs.append({"job_id": None, "job_url": url})
        return refs

itviec_crawler = ITViecCrawler()
