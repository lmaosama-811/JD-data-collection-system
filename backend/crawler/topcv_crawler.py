import json
import re
import time
# pyrefly: ignore[missing-import]
from bs4 import BeautifulSoup
# pyrefly: ignore[missing-import]
from curl_cffi import requests
from .crawler_base import CrawlerBase, RAW_DATA_ROOT
from backend.config.log_config import get_logger

logger = get_logger(__name__)


class TopCVCrawler(CrawlerBase):
    file_path = RAW_DATA_ROOT / "topcv"
    BASE_URL = "https://www.topcv.vn/"
    DELAY_PER_REQUESTS = 3.0

    def __init__(self, impersonate: str = "chrome124", headless: bool = False):
        self.impersonate = impersonate
        self.headless = headless
        self.csrf_token = None
        self.user_agent = None
        self._session = None

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = self._create_session()
        return self._session

    @session.setter
    def session(self, value: requests.Session):
        self._session = value

    def _fetch_browser_credentials(self, timeout_s: int = 45) -> dict:
        """
        Mở Chromium (Playwright), vào trang chủ TopCV, đợi vượt Cloudflare (cf_clearance),
        rồi trả về cookies, CSRF token (meta csrf-token) và User-Agent thật của trình duyệt.
        """
        # pyrefly: ignore[missing-import]
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            try:
                context = browser.new_context(locale="vi-VN")
                page = context.new_page()
                page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=timeout_s * 1000)

                # Đợi cf_clearance + thẻ meta csrf-token xuất hiện (tức là đã qua challenge)
                deadline = time.time() + timeout_s
                csrf = None
                while time.time() < deadline:
                    csrf = page.evaluate(
                        "() => { const m = document.querySelector('meta[name=\"csrf-token\"]');"
                        " return m ? m.content : null; }"
                    )
                    names = {c["name"] for c in context.cookies()}
                    if csrf and ("cf_clearance" in names or "topcv_session" in names):
                        break
                    page.wait_for_timeout(1000)

                if not csrf:
                    raise RuntimeError("Không lấy được CSRF token (có thể bị Cloudflare chặn)")

                return {
                    "cookies": {c["name"]: c["value"] for c in context.cookies()},
                    "csrf": csrf,
                    "user_agent": page.evaluate("() => navigator.userAgent"),
                }
            finally:
                browser.close()

    def _create_session(self) -> requests.Session:
        session = requests.Session(impersonate=self.impersonate)

        logger.info("Khởi tạo session TopCV: mở trình duyệt lấy cookie/CSRF (headless=%s)", self.headless)
        t0 = time.perf_counter()
        creds = self._fetch_browser_credentials()
        logger.info("Lấy credentials TopCV xong trong %.1fs (%d cookies)", time.perf_counter() - t0, len(creds["cookies"]))
        session.cookies.update(creds["cookies"])
        self.csrf_token = creds["csrf"]
        self.user_agent = creds["user_agent"]

        # sec-ch-ua khớp phiên bản Chrome trong User-Agent đã dùng
        m = re.search(r"Chrome/(\d+)", self.user_agent)
        ver = m.group(1) if m else "124"

        # Thiết lập headers mặc định
        session.headers.update({
            "authority": "www.topcv.vn",
            "accept-language": "en-US,en;q=0.9,vi;q=0.8",
            "sec-ch-ua": f'"Google Chrome";v="{ver}", "Chromium";v="{ver}", "Not(A:Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "user-agent": self.user_agent
        })
        return session

    def search_jobs(self, keyword="software-engineer", page=1) -> dict:
        # Truy cập session TRƯỚC khi dựng headers: session khởi tạo lazy, và chính lúc tạo
        # nó mới lấy được self.csrf_token / self.user_agent từ trình duyệt.
        session = self.session

        url = f"https://www.topcv.vn/tim-viec-lam-{keyword}?page={page}&type_keyword=1&sba=1&saturday_status=0"
    
        headers = {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "origin": "https://www.topcv.vn",
            "referer": url,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest"
        }

        raw = self._request("POST", url, "TopCV search", headers=headers, data=b"")
        result = self._extract_search(raw)
        logger.info("TopCV search: keyword='%s', page=%d, %d job (tổng %s)", keyword, page, len(result["items"]), result["meta"].get("total"))
        return result

    def crawl_job_detail(self, job_url: str = None, job_id: str = None) -> dict:
        if not job_url:
            raise ValueError("TopCVCrawler.crawl_job_detail requires job_url")
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "upgrade-insecure-requests": "1"
        }

        raw = self._request("GET", job_url, "TopCV detail", headers=headers)
        return self._extract_detail(raw)

    @classmethod
    def _tooltip_lines(cls, html_title: str) -> list[str]:
        if not html_title:
            return []
        text = BeautifulSoup(html_title, "html.parser").get_text("\n")
        return [" ".join(line.split()) for line in text.split("\n") if line.strip()]

    @classmethod
    def _parse_search_card(cls, card) -> dict:
        title_a = card.select_one("h3.title > a") or card.select_one("h3.title a")
        title_span = title_a.select_one("span") if title_a else None
        company_a = card.select_one("a.company")
        address_a = card.select_one(".label-content a.address")
        update_label = card.select_one("label.label-update")
        verified = card.select_one(".icon-verified-employer")
        avatar_img = card.select_one(".avatar img")
        tag_block = card.select_one(".box-icon .tag")

        tags = {"links": [], "texts": [], "more": None}
        if tag_block is not None:
            for a in tag_block.select("a.item-tag"):
                tags["links"].append({
                    "text": cls._text(a),
                    "href": a.get("href"),
                    "title": a.get("title"),
                })
            tags["texts"] = [cls._text(s) for s in tag_block.select("span.item-tag")]
            more = tag_block.select_one(".remaining-items")
            if more is not None:
                tags["more"] = {"label": cls._text(more), "tooltip": more.get("title")}

        classes = card.get("class", [])
        return {
            "job_id": card.get("data-job-id"),
            "job_url": cls._clean_url(title_a.get("href")) if title_a else None,
            "title": cls._text(title_span) or (title_a.get("title") if title_a else None),
            "labels": [cls._text(l) for l in card.select("h3.title .box-label-top label") if cls._text(l)],
            "promotion_classes": [c for c in classes if c.startswith("bg-")],
            "is_flash_job": "bg-flash-job" in classes,
            "is_diamond_employer": card.select_one(".tag-diamond-employer") is not None,
            "verified_employer": ({
                "levels": [c for c in verified.get("class", []) if c.startswith("level-")],
                "tooltip_lines": cls._tooltip_lines((verified.select_one("[title]") or verified).get("title")),
            } if verified is not None else None),
            "company": {
                "name": cls._text(card.select_one(".company-name")),
                "url": cls._clean_url(company_a.get("href")) if company_a else None,
                "logo": (avatar_img.get("data-src") or avatar_img.get("src")) if avatar_img else None,
            },
            "salary_text": cls._text(card.select_one(".label-content label.salary")),
            "city_text": cls._text(card.select_one(".label-content .city-text")),
            "locations": cls._tooltip_lines_li(address_a.get("title")) if address_a else [],
            "experience_text": cls._text(card.select_one(".label-content label.exp")),
            "tags": tags,
            "posted_text": cls._text(update_label),
            "updated_text": update_label.get("title") if update_label else None,
        }

    @classmethod
    def _tooltip_lines_li(cls, html_title: str) -> list[str]:
        """Tooltip địa điểm của card: lấy các <li> (mỗi <li> là 1 thành phố)."""
        if not html_title:
            return []
        return [cls._text(li) for li in BeautifulSoup(html_title, "html.parser").find_all("li")]

    def _extract_search(self, raw: str) -> dict:
        payload = json.loads(raw)
        if payload.get("status") != "success":
            raise ValueError(f"TopCV search status={payload.get('status')}: {payload.get('message')}")
        data = payload.get("data") or {}

        soup = BeautifulSoup(data.get("html_job", ""), "lxml")
        items = [self._parse_search_card(c) for c in soup.select("div.job-item-search-result")]
        return {
            "meta": {
                "total": data.get("total"),
                "total_page": data.get("total_page"),
                "current_page": data.get("current_page"),
                "count_job_flash": data.get("count_job_flash"),
                "params": data.get("params"),
            },
            "items": items,
        }

    def _extract_detail(self, raw: str) -> dict:
        soup = BeautifulSoup(raw, "lxml")

        job_posting = None
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                parsed = json.loads(s.string or "")
            except (ValueError, TypeError):
                continue
            candidates = parsed if isinstance(parsed, list) else [parsed]
            for item in candidates:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    job_posting = item
                    break
            if job_posting:
                break
        if job_posting is None:
            raise ValueError("TopCV detail: không tìm thấy JSON-LD JobPosting (trang có thể bị chặn/đổi cấu trúc)")
        job_posting = {k: v for k, v in job_posting.items() if k != "employerOverview"}

        t = self._text

        # Header: tên công ty, tag trong h1, lương hiển thị, các mục thông tin (Địa điểm / Kinh nghiệm ...)
        header_company = soup.select_one(".box-header-job .box-company-info")
        header = {
            "title_tags": [{"text": t(a), "href": a.get("href")} for a in soup.select("h1.box-header-job__title a")],
            "salary_text": t(soup.select_one(".box-header-job__salary--title")),
            "info_items": [
                {
                    "label": t(it.select_one(".list-info__content__title")),
                    "value": t(it.select_one(".list-info__content__desc")),
                }
                for it in soup.select(".box-header-job-list-info__item")
            ],
        }

        general_info = [
            {
                "label": t(it.select_one("[class*='content-title']")),
                "value": t(it.select_one("[class*='content-desc']")),
            }
            for it in soup.select(".box-job-information-general-info-list__item")
        ]

        address_and_time = []
        for it in soup.select(".box-job-information-address-and-time-list__item"):
            label_el = it.select_one("[class*='item--title']")
            if label_el is None:
                continue  # khối nút "Ứng tuyển ngay / Lưu tin" (không có nhãn) -> lấy hạn ứng tuyển riêng bên dưới
            address_and_time.append({
                "label": t(label_el),
                "values": [t(li) for li in it.select("[class*='item--content'] li")] or [t(it.select_one("[class*='item--content']"))],
            })

        job_tags = []
        for g in soup.select(".job-tags__group"):
            job_tags.append({
                "label": t(g.select_one(".job-tags__group-name")),
                "tags": [{"text": t(a), "href": a.get("href"), "title": a.get("title")} for a in g.select("a.item")],
            })

        required_tags = [
            {"label": t(r.select_one("[class*='content--title']")), "value": t(r.select_one("[class*='content--desc']"))}
            for r in soup.select(".required-tag")
        ]

        category_tags = [
            [{"text": t(a), "href": a.get("href"), "title": a.get("title")} for a in grp.select("a.box-category-tag")]
            for grp in soup.select(".box-category-tags")
        ]

        company_link = header_company.select_one("a.name") if header_company else None
        company_logo = header_company.select_one("img") if header_company else None
        company = {
            "name": t(company_link),
            "url": company_link.get("href") if company_link else None,
            "logo": company_logo.get("src") if company_logo else None,
            "details": [
                {
                    "label": t(it.select_one("[class*='item-label']")),
                    "values": [t(v) for v in it.select("[class*='item-value']")],
                }
                for it in soup.select(".box-company-info-detail__list--item")
            ],
        }

        deadline_el = soup.select_one(".box-applied-cv")
        verified_post = soup.select_one(".box-verified-post")

        return {
            "job_posting": job_posting,
            "header": header,
            "general_info": general_info,
            "address_and_time": address_and_time,
            "job_tags": job_tags,
            "required_tags": required_tags,
            "category_tags": category_tags,
            "company": company,
            "deadline_text": t(deadline_el),
            "verified_post_text": t(verified_post),
        }

    def get_job_refs(self, search_result: dict) -> list[dict]:
        """Từ kết quả search_jobs/_extract_search, trích job_id + job_url (đã bỏ query tracking)."""
        refs, seen = [], set()
        for item in search_result.get("items", []):
            job_id, job_url = item.get("job_id"), item.get("job_url")
            key = job_id or job_url
            if key and key not in seen:
                seen.add(key)
                refs.append({"job_id": job_id, "job_url": job_url})
        return refs

topcv_crawler = TopCVCrawler()
