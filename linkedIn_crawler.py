"""
LinkedIn Job Crawler (Production-ready Guest API Pipeline)
Architecture:
1. Guest Search API: GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
   - Scrapes job cards from HTML <li> fragments.
   - Extracts numeric `job_id`, `title`, `company`, `location`, `posted_time_ago`.
2. Guest Detail API: GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}
   - Fetches full job detail HTML fragment.
   - Extracts: Full Job Description, Seniority, Employment Type, Industries, Applicants, Company URL.
3. Defense & Resilience:
   - Auto-detects HTTP 429 Too Many Requests (Guest Wall) and executes Cooldown sleep (15-20s).
   - Chrome 124 TLS Impersonation via curl_cffi.
   - Optional Cookie Injection (li_at, JSESSIONID, bcookie) for authenticated higher-rate scraping.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup, SoupStrainer
from curl_cffi import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("LinkedInCrawler")


class LinkedInCrawler:
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

    def __init__(
        self,
        cookies: Optional[Dict[str, str]] = None,
        impersonate: str = "chrome124",
        timeout: int = 15
    ):
        self.impersonate = impersonate
        self.timeout = timeout
        self.cookies = cookies or {}
        self.session = self._create_session()
        self.li_strainer = SoupStrainer("li")

    def _create_session(self) -> requests.Session:
        s = requests.Session(impersonate=self.impersonate)
        if self.cookies:
            for k, v in self.cookies.items():
                s.cookies.set(k, v, domain=".linkedin.com")
        return s

    def _get_with_cooldown(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
        cooldown_seconds: float = 16.0
    ) -> Optional[requests.Response]:
        """
        Executes request with detection of HTTP 429 Too Many Requests.
        If 429 is encountered, sleeps for cooldown_seconds and retries with a fresh TLS session.
        """
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(
                    url,
                    params=params,
                    headers=self.DEFAULT_HEADERS,
                    timeout=self.timeout
                )
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 429:
                    logger.warning(
                        f"LinkedIn Rate Limit (HTTP 429) hit on attempt {attempt}/{retries}. "
                        f"Cooldown sleeping for {cooldown_seconds:.1f}s..."
                    )
                    time.sleep(cooldown_seconds)
                    # Reset session to clear challenge socket
                    self.session = self._create_session()
                elif resp.status_code in (404, 410):
                    logger.warning(f"Resource {url} not found (HTTP {resp.status_code})")
                    return resp
                else:
                    logger.warning(f"Unexpected HTTP {resp.status_code} for {url}: {resp.text[:120]}")
            except Exception as e:
                logger.warning(f"Network error on attempt {attempt}/{retries} for {url}: {e}")
                time.sleep(2.0 * attempt)
                self.session = self._create_session()

        return None

    def fetch_search_listings(
        self,
        keywords: str = "Python",
        location: str = "Vietnam",
        start: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Calls Guest Search API:
        https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=...&location=...&start=...
        """
        params = {
            "keywords": keywords,
            "location": location,
            "start": start
        }
        logger.info(f"Calling Guest Search API: keywords='{keywords}', location='{location}', start={start}")
        t0 = time.perf_counter()
        resp = self._get_with_cooldown(self.SEARCH_API_URL, params=params)
        fetch_ms = (time.perf_counter() - t0) * 1000

        if not resp or resp.status_code != 200:
            logger.error(f"Search API failed after retries (Status: {getattr(resp, 'status_code', 'No response')})")
            return []

        soup = BeautifulSoup(resp.text, "lxml", parse_only=self.li_strainer)
        cards = soup.find_all("li")
        results = []

        for li in cards:
            card_div = li.find(class_=re.compile(r"base-card|job-search-card"))
            entity_urn = card_div.get("data-entity-urn") if card_div else None
            
            link = li.find("a", class_=re.compile(r"base-card__full-link|job-search-card__title-link"))
            href = link.get("href") if link else None
            title = link.get_text(strip=True) if link else (li.find("h3").get_text(strip=True) if li.find("h3") else "")

            # Extract job ID
            job_id = None
            if entity_urn:
                m = re.search(r"jobPosting:(\d+)", entity_urn)
                if m:
                    job_id = m.group(1)
            if not job_id and href:
                m = re.search(r"/view/[^/]*?(\d+)", href) or re.search(r"-(\d+)\?", href) or re.search(r"/jobs/view/(\d+)", href)
                if m:
                    job_id = m.group(1)

            if not job_id:
                continue

            company_tag = li.find("h4")
            company = company_tag.get_text(strip=True) if company_tag else ""
            location_tag = li.find(class_=re.compile(r"job-search-card__location"))
            loc = location_tag.get_text(strip=True) if location_tag else ""
            time_tag = li.find("time")
            posted_time = time_tag.get_text(strip=True) if time_tag else ""

            results.append({
                "job_id": job_id,
                "title": title,
                "company": company,
                "location": loc,
                "job_url": href.split("?")[0] if href else f"https://www.linkedin.com/jobs/view/{job_id}",
                "posted_time_ago": posted_time
            })

        logger.info(f"Search API parsed {len(results)} jobs in {fetch_ms:.1f}ms")
        return results

    def fetch_job_detail(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Calls Guest Detail API:
        https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}
        """
        url = self.DETAIL_API_URL.format(job_id=job_id)
        logger.info(f"Calling Guest Detail API for Job {job_id}")
        t0 = time.perf_counter()
        resp = self._get_with_cooldown(url)
        fetch_ms = (time.perf_counter() - t0) * 1000

        if not resp or resp.status_code != 200:
            logger.warning(f"Detail API failed for Job {job_id} (Status: {getattr(resp, 'status_code', 'No response')})")
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        # Title
        title_elem = soup.find(class_=re.compile(r"topcard__title|top-card-layout__title"))
        title = title_elem.get_text(strip=True) if title_elem else ""

        # Company
        company_elem = soup.find(class_=re.compile(r"topcard__org-name-link|top-card-layout__first-sub-headline"))
        company = company_elem.get_text(strip=True) if company_elem else ""
        company_url = company_elem.get("href") if company_elem else None

        # Location
        loc_elem = soup.find(class_=re.compile(r"topcard__flavor--bullet|top-card-layout__second-sub-headline"))
        location = loc_elem.get_text(strip=True) if loc_elem else ""

        # Posted Time & Applicants
        posted_elem = soup.find(class_=re.compile(r"posted-time-ago__text"))
        posted_time = posted_elem.get_text(strip=True) if posted_elem else ""
        num_app_elem = soup.find(class_=re.compile(r"num-applicants__caption|num-applicants"))
        applicants = num_app_elem.get_text(strip=True) if num_app_elem else ""

        # Criteria (Seniority, Employment type, Job function, Industries)
        criteria = {}
        for item in soup.find_all(class_=re.compile(r"description__job-criteria-item|job-criteria__item")):
            h = item.find(class_=re.compile(r"subheader|title"))
            v = item.find(class_=re.compile(r"text|value"))
            if h and v:
                criteria[h.get_text(strip=True)] = v.get_text(strip=True)

        # Description
        desc_elem = soup.find(class_=re.compile(r"show-more-less-html__markup|description__text"))
        desc_html = str(desc_elem) if desc_elem else ""
        desc_text = desc_elem.get_text(separator="\n", strip=True) if desc_elem else ""

        logger.info(f"Detail API success for Job {job_id} in {fetch_ms:.1f}ms (Desc len: {len(desc_text)} chars)")
        return {
            "title": title,
            "company": company,
            "company_url": company_url,
            "location": location,
            "posted_time_ago": posted_time,
            "applicants": applicants,
            "criteria": criteria,
            "job_description_html": desc_html,
            "job_description_text": desc_text,
            "detail_latency_ms": round(fetch_ms, 2)
        }

    def crawl_jobs(
        self,
        keywords: str = "Python",
        location: str = "Vietnam",
        limit_jobs: int = 2,
        delay_between_requests: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        Crawl pipeline:
        1. Fetch search listings
        2. Fetch detail for each job
        3. Merge consolidated record
        """
        listings = self.fetch_search_listings(keywords=keywords, location=location, start=0)
        if not listings:
            logger.error("No listings retrieved from LinkedIn. Stopping.")
            return []

        target_listings = listings[:limit_jobs]
        logger.info(f"Processing {len(target_listings)} jobs from search listings...")

        all_jobs = []
        for idx, item in enumerate(target_listings, 1):
            job_id = item["job_id"]
            
            # Safe polite delay between detail calls
            if delay_between_requests > 0:
                time.sleep(delay_between_requests)

            detail = self.fetch_job_detail(job_id)
            if not detail:
                continue

            record = {
                "source": "linkedin",
                "job_id": job_id,
                "title": detail.get("title") or item.get("title"),
                "company": {
                    "name": detail.get("company") or item.get("company"),
                    "url": detail.get("company_url")
                },
                "location": detail.get("location") or item.get("location"),
                "posted_time_ago": detail.get("posted_time_ago") or item.get("posted_time_ago"),
                "applicants": detail.get("applicants"),
                "criteria": detail.get("criteria", {}),
                "job_url": item.get("job_url"),
                "job_description_text": detail.get("job_description_text", ""),
                "job_description_html": detail.get("job_description_html", ""),
                "detail_latency_ms": detail.get("detail_latency_ms")
            }

            all_jobs.append(record)
            logger.info(f"[{idx}/{len(target_listings)}] Finished Job {job_id} ('{record['title']}')")

        return all_jobs


if __name__ == "__main__":
    crawler = LinkedInCrawler()
    print("=" * 60)
    print("STARTING LINKEDIN CRAWLER TEST RUN (2 Jobs Sample)")
    print("=" * 60)

    t_start = time.perf_counter()
    crawled_data = crawler.crawl_jobs(
        keywords="Python",
        location="Vietnam",
        limit_jobs=5,
        delay_between_requests=2.0
    )
    total_duration = time.perf_counter() - t_start

    output_file = "linkedin_test_output.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(crawled_data, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"CRAWL COMPLETE in {total_duration:.2f}s!")
    print(f"Saved {len(crawled_data)} jobs to '{output_file}'")
    for job in crawled_data:
        print(f"\n- Job ID: {job['job_id']}")
        print(f"  Title: {job['title']} | Company: {job['company']['name']}")
        print(f"  Location: {job['location']} | Posted: {job['posted_time_ago']}")
        print(f"  Criteria: {job['criteria']}")
        print(f"  Desc Length: {len(job['job_description_text'])} chars")
        print(f"  Desc Preview: {job['job_description_text'][:140].replace(chr(10), ' ')}...")
    print("=" * 60)
