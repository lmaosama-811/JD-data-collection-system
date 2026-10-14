"""
NodeFlair Rate Limit & Cloudflare WAF Benchmark (Pure REST API Architecture)
Benchmarks:
1. End-to-End Pipeline Simulation (Search + Detail API with safe 0.5s delay)
2. Search Listing API Burst Test: GET /api/v2/jobs (0.0s delay)
3. Detail REST API Burst Test: GET /api/v2/jobs/{id} (0.0s delay)
"""

import time
import statistics
from typing import List, Dict, Any
from curl_cffi import requests

HEADERS_API = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,vi;q=0.8",
    "origin": "https://nodeflair.com",
    "referer": "https://nodeflair.com/jobs",
}


class NodeFlairClient:
    def __init__(self, impersonate: str = "chrome124"):
        self.impersonate = impersonate
        self.session = requests.Session(impersonate=impersonate)

    def get_with_retry(self, url: str, retries: int = 3, timeout: int = 10, **kwargs) -> requests.Response:
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                return self.session.get(url, timeout=timeout, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < retries:
                    time.sleep(1.0 * attempt)
                    self.session = requests.Session(impersonate=self.impersonate)
        raise last_error


def _print_stats(test_name: str, latencies: List[float], status_counts: Dict[Any, int], total: int):
    print("-" * 55, flush=True)
    print(f"SUMMARY FOR {test_name}:", flush=True)
    print(f"Total Requests: {total}")
    print(f"Status Distribution: {status_counts}")
    if latencies:
        print(f"Min Latency: {min(latencies):.1f}ms")
        print(f"Avg Latency: {statistics.mean(latencies):.1f}ms")
        print(f"Max Latency: {max(latencies):.1f}ms")
        if len(latencies) > 1:
            print(f"Median Latency: {statistics.median(latencies):.1f}ms")
    print("-" * 55, flush=True)


def test_pipeline_simulation(client: NodeFlairClient, total_jobs: int = 3, delay: float = 0.5):
    print("\n" + "=" * 60, flush=True)
    print(f"BENCHMARK 1: PIPELINE SIMULATION ({total_jobs} jobs, {delay}s safe delay)", flush=True)
    print("Goal: Verify production crawling stability and latency", flush=True)
    print("=" * 60, flush=True)

    t_start = time.perf_counter()
    params = {"query": "software", "page": 1, "countries[]": "Vietnam"}
    resp = client.get_with_retry("https://nodeflair.com/api/v2/jobs", params=params, headers=HEADERS_API)
    if resp.status_code != 200:
        print(f"Pipeline failed at Search API with status {resp.status_code}")
        return

    listings = resp.json().get("job_listings", [])[:total_jobs]
    print(f"Received {len(listings)} jobs from Search API. Fetching details with {delay}s delay...\n", flush=True)

    latencies = []
    success_count = 0

    for idx, item in enumerate(listings, 1):
        job_id = item.get("id")
        t0 = time.perf_counter()
        try:
            r = client.get_with_retry(f"https://nodeflair.com/api/v2/jobs/{job_id}", headers=HEADERS_API)
            latency = (time.perf_counter() - t0) * 1000
            latencies.append(latency)

            if r.status_code == 200:
                success_count += 1
                job_obj = r.json().get("job", {})
                desc_len = len(job_obj.get("description", "") or "")
                yoe = f"YOE: {job_obj.get('yoe_min')}-{job_obj.get('yoe_max')}"
                print(f"[{idx}/{len(listings)}] Job {job_id}: Status 200 | Latency: {latency:.1f}ms | {yoe} | Desc: {desc_len} chars", flush=True)
            else:
                print(f"[{idx}/{len(listings)}] Job {job_id}: Status {r.status_code} | Latency: {latency:.1f}ms", flush=True)
        except Exception as e:
            print(f"[{idx}/{len(listings)}] Job {job_id}: Timeout/Error: {e}", flush=True)

        if idx < len(listings) and delay > 0:
            time.sleep(delay)

    total_pipeline_ms = (time.perf_counter() - t_start) * 1000
    print("-" * 55, flush=True)
    print("PIPELINE SIMULATION RESULTS:", flush=True)
    print(f"Total Duration: {total_pipeline_ms/1000:.2f}s")
    print(f"Success Rate: {success_count}/{len(listings)} ({(success_count/len(listings))*100:.0f}%)")
    if latencies:
        print(f"Avg Detail API Latency: {statistics.mean(latencies):.1f}ms")
    print("-" * 55, flush=True)


def test_search_api_burst(client: NodeFlairClient, total_requests: int = 4):
    print("\n" + "=" * 60, flush=True)
    print(f"BENCHMARK 2: SEARCH API BURST ({total_requests} requests, 0.0s delay)", flush=True)
    print("Goal: Observe Cloudflare TCP tarpitting threshold on Search API", flush=True)
    print("=" * 60, flush=True)

    latencies = []
    status_counts = {}

    for i in range(1, total_requests + 1):
        params = {
            "query": "software",
            "page": i,
            "sort_by": "relevant",
            "countries[]": "Vietnam"
        }
        t0 = time.perf_counter()
        try:
            resp = client.session.get(
                "https://nodeflair.com/api/v2/jobs",
                params=params,
                headers=HEADERS_API,
                timeout=6
            )
            latency = (time.perf_counter() - t0) * 1000
            latencies.append(latency)
            status = resp.status_code
            status_counts[status] = status_counts.get(status, 0) + 1

            items_count = len(resp.json().get("job_listings", [])) if status == 200 else 0
            tarpit_flag = " [TARPIT/DELAYED]" if latency > 3000 else ""
            print(f"Search Req #{i:02d}: Status {status} | Latency: {latency:.1f}ms | Items: {items_count}{tarpit_flag}", flush=True)
        except Exception as e:
            err_name = type(e).__name__
            print(f"Search Req #{i:02d}: {err_name} (Tarpit drop)", flush=True)
            status_counts["TIMEOUT"] = status_counts.get("TIMEOUT", 0) + 1

    _print_stats("Search API Burst (0.0s delay)", latencies, status_counts, total_requests)


def test_detail_api_burst(client: NodeFlairClient, sample_job_ids: List[int]):
    print("\n" + "=" * 60, flush=True)
    print(f"BENCHMARK 3: DETAIL REST API BURST ({len(sample_job_ids)} requests, 0.0s delay)", flush=True)
    print("Goal: Observe Cloudflare rate limiting on Detail endpoint", flush=True)
    print("=" * 60, flush=True)

    latencies = []
    status_counts = {}

    for idx, job_id in enumerate(sample_job_ids, 1):
        url = f"https://nodeflair.com/api/v2/jobs/{job_id}"
        t0 = time.perf_counter()
        try:
            resp = client.session.get(url, headers=HEADERS_API, timeout=6)
            latency = (time.perf_counter() - t0) * 1000
            latencies.append(latency)
            status = resp.status_code
            status_counts[status] = status_counts.get(status, 0) + 1

            if status == 200:
                data = resp.json()
                job = data.get("job", {})
                title = job.get("title", "")
                desc_len = len(job.get("description", "") or "")
                print(f"Detail Req #{idx:02d} (ID {job_id}): Status {status} | Latency: {latency:.1f}ms | '{title[:25]}' | Desc: {desc_len} chars", flush=True)
            else:
                print(f"Detail Req #{idx:02d} (ID {job_id}): Status {status} | Latency: {latency:.1f}ms", flush=True)
        except Exception as e:
            err_name = type(e).__name__
            print(f"Detail Req #{idx:02d} (ID {job_id}): {err_name} (Tarpit drop)", flush=True)
            status_counts["TIMEOUT"] = status_counts.get("TIMEOUT", 0) + 1

    _print_stats("Detail REST API Burst (0.0s delay)", latencies, status_counts, len(sample_job_ids))


if __name__ == "__main__":
    client = NodeFlairClient(impersonate="chrome124")
    print("=" * 60, flush=True)
    print("STARTING NODEFLAIR PURE REST API BENCHMARK SUITE", flush=True)
    print("=" * 60, flush=True)

    # 1. Pipeline simulation (production recommendation)
    test_pipeline_simulation(client, total_jobs=3, delay=0.5)

    # Cooldown 1.0s
    time.sleep(1.0)

    # 2. Search API burst
    test_search_api_burst(client, total_requests=4)

    # Cooldown 1.0s
    time.sleep(1.0)

    # 3. Detail API burst
    sample_ids = [553228, 552673, 550724]
    test_detail_api_burst(client, sample_job_ids=sample_ids)

    print("\nBENCHMARK SUITE COMPLETED SUCCESSFULLY.", flush=True)
