"""
NodeFlair Job Crawler (Streamlined Pure REST API)
Architecture:
1. Search Listing API: GET https://nodeflair.com/api/v2/jobs?query=...&page=...&countries[]=Vietnam
   - Returns structured listings: id, title, position, salary, tech_stacks, seniority, company.
2. Detail REST API: GET https://nodeflair.com/api/v2/jobs/{job_id}
   - Returns clean structured JSON: description (HTML), yoe_min, yoe_max, employment_type.
   - Eliminates HTML slug scraping, eliminating all 404 ambiguity and saving 90% bandwidth.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from curl_cffi import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("NodeFlairCrawler")


class NodeFlairCrawler:
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

    def __init__(self, impersonate: str = "chrome124", timeout: int = 15):
        self.impersonate = impersonate
        self.timeout = timeout
        self.session = requests.Session(impersonate=impersonate)

    def _get_with_retry(self, url: str, retries: int = 3, **kwargs) -> requests.Response:
        """Retry logic with exponential backoff on transient network drops."""
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout
                return self.session.get(url, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(f"Request failed (attempt {attempt}/{retries}) for {url}: {e}")
                if attempt < retries:
                    time.sleep(1.0 * attempt)
                    self.session = requests.Session(impersonate=self.impersonate)
        raise last_error

    def fetch_search_listings(
        self,
        query: str = "software",
        page: int = 1,
        sort_by: str = "relevant",
        country: str = "Vietnam"
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Fetch structured job items from Search Listing API.
        """
        params = {
            "query": query,
            "page": page,
            "sort_by": sort_by,
            "countries[]": country
        }

        logger.info(f"Calling Search API: query='{query}', page={page}, country='{country}'")
        t0 = time.perf_counter()
        resp = self._get_with_retry(
            self.SEARCH_API_URL,
            params=params,
            headers=self.HEADERS_API
        )
        latency = (time.perf_counter() - t0) * 1000

        if resp.status_code != 200:
            logger.error(f"Search API failed with status {resp.status_code}: {resp.text[:300]}")
            return [], 0

        data = resp.json()
        listings = data.get("job_listings", [])
        total_count = data.get("total_listings_count", len(listings))
        logger.info(f"Search API success in {latency:.1f}ms: received {len(listings)} jobs (Total available: {total_count})")
        return listings, total_count

    def fetch_job_detail(self, job_id: int) -> Optional[Dict[str, Any]]:
        """
        Direct Detail REST API call.
        Returns job details if HTTP 200, None if HTTP 404 or any other error.
        """
        api_url = self.DETAIL_API_URL.format(job_id=job_id)
        t0 = time.perf_counter()
        resp = self._get_with_retry(api_url, headers=self.HEADERS_API)
        api_ms = (time.perf_counter() - t0) * 1000

        if resp.status_code != 200:
            logger.warning(f"Job {job_id} not available (HTTP {resp.status_code})")
            return None

        job = resp.json().get("job", {})
        desc_html = job.get("description", "") or ""
        soup = BeautifulSoup(desc_html, "html.parser")

        logger.info(f"Detail API success for Job {job_id} in {api_ms:.1f}ms")
        return {
            "description_html": desc_html,
            "description_text": soup.get_text(separator="\n", strip=True),
            "yoe_min": job.get("yoe_min"),
            "yoe_max": job.get("yoe_max"),
            "employment_type": job.get("employment_type"),
            "latency_ms": round(api_ms, 2)
        }

    def crawl_jobs(
        self,
        query: str = "software",
        max_pages: int = 1,
        limit_per_page: Optional[int] = 5,
        delay_between_requests: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Pure REST API crawl pipeline:
        1. Fetch search listings
        2. Fetch full detail via REST API
        3. Merge clean structured data
        """
        all_jobs = []

        for page in range(1, max_pages + 1):
            listings, total_count = self.fetch_search_listings(query=query, page=page)
            if not listings:
                logger.info(f"No listings found on page {page}. Stopping.")
                break

            target_listings = listings[:limit_per_page] if limit_per_page else listings
            logger.info(f"Processing {len(target_listings)} jobs from page {page}...")

            for idx, item in enumerate(target_listings, 1):
                job_id = item.get("id")
                job_path = item.get("job_path", "")
                title = item.get("title", "")
                company_info = item.get("company", {}) or {}

                # Fetch detail via clean REST API
                detail = self.fetch_job_detail(job_id)
                if not detail:
                    logger.warning(f"Skipping job {job_id} ('{title}') because detail was not found.")
                    continue

                # Build consolidated job record
                job_record: Dict[str, Any] = {
                    "source": "nodeflair",
                    "job_id": job_id,
                    "title": title,
                    "position": item.get("position"),
                    "seniority": item.get("seniority", []),
                    "tech_stacks": [t.get("name") for t in item.get("tech_stacks", []) if isinstance(t, dict)],
                    "experience": {
                        "yoe_min": detail.get("yoe_min"),
                        "yoe_max": detail.get("yoe_max")
                    },
                    "employment_type": detail.get("employment_type"),
                    "salary": {
                        "min": item.get("salary_min"),
                        "max": item.get("salary_max"),
                        "currency": item.get("currency"),
                        "frequency": item.get("remuneration_frequency"),
                        "formatted_min": item.get("formatted_salary_min"),
                        "formatted_max": item.get("formatted_salary_max"),
                        "is_estimated": item.get("is_salary_estimated", False)
                    },
                    "company": {
                        "id": company_info.get("id"),
                        "name": company_info.get("companyname"),
                        "rating": company_info.get("rating"),
                        "avatar_url": company_info.get("avatar")
                    },
                    "country": item.get("country", "Vietnam"),
                    "posted_time_ago": item.get("time_ago"),
                    "job_url": f"{self.BASE_URL}{job_path.split('?')[0]}" if job_path else "",
                    "job_description_text": detail.get("description_text", ""),
                    "job_description_html": detail.get("description_html", ""),
                    "detail_latency_ms": detail.get("latency_ms")
                }

                all_jobs.append(job_record)
                logger.info(f"[{idx}/{len(target_listings)}] Finished Job {job_id} ('{title}')")

                if delay_between_requests > 0:
                    time.sleep(delay_between_requests)

        return all_jobs


if __name__ == "__main__":
    crawler = NodeFlairCrawler()
    print("=" * 60)
    print("STARTING NODEFLAIR CRAWLER (Pure REST API - 2 Jobs)")
    print("=" * 60)

    t_start = time.perf_counter()
    crawled_data = crawler.crawl_jobs(
        query="software",
        max_pages=1,
        limit_per_page=2,
        delay_between_requests=0.5
    )
    total_duration = time.perf_counter() - t_start

    output_file = "nodeflair_test_output.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(crawled_data, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"CRAWL COMPLETE in {total_duration:.2f}s!")
    print(f"Saved {len(crawled_data)} jobs to '{output_file}'")
    for job in crawled_data:
        print(f"\n- Job ID: {job['job_id']}")
        print(f"  Title: {job['title']} | Company: {job['company']['name']}")
        print(f"  Tech Stacks: {job['tech_stacks']}")
        print(f"  Seniority: {job['seniority']} | Exp: {job.get('experience')}")
        print(f"  Salary: {job['salary']['formatted_min']} - {job['salary']['formatted_max']} {job['salary']['currency']}")
        print(f"  Detail API Latency: {job.get('detail_latency_ms')}ms")
        print(f"  Desc Length: {len(job.get('job_description_text', ''))} chars")
        print(f"  Desc Preview: {job.get('job_description_text', '')[:140].replace(chr(10), ' ')}...")
    print("=" * 60)
