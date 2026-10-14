"""
LinkedIn Rate Limit & Anti-Scraping Benchmark Suite
Evaluates LinkedIn Guest APIs:
1. Burst Mode (0.0s delay): Demonstrates immediate HTTP 429 (Too Many Requests) guest wall
2. Auto-Cooldown Recovery: Verifies how fast the IP rate limit recovers (15s cooldown)
3. Polite Mode (2.5s delay): Tests production scraping stability
"""

import time
import statistics
from typing import List, Dict, Any
from curl_cffi import requests

HEADERS_BASE = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "accept-language": "en-US,en;q=0.9,vi;q=0.8",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


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


def test_burst_mode(session: requests.Session, total_requests: int = 5):
    print("\n" + "=" * 60, flush=True)
    print(f"BENCHMARK 1: BURST MODE ({total_requests} requests, 0.0s delay)", flush=True)
    print("Goal: Observe LinkedIn's strict Guest Rate Limit (HTTP 429)", flush=True)
    print("Endpoint: https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search", flush=True)
    print("=" * 60, flush=True)

    latencies = []
    status_counts = {}

    for i in range(1, total_requests + 1):
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=Python&location=Vietnam&start={(i-1)*10}"
        t0 = time.perf_counter()
        try:
            resp = session.get(url, headers=HEADERS_BASE, timeout=10)
            latency = (time.perf_counter() - t0) * 1000
            latencies.append(latency)
            status = resp.status_code
            status_counts[status] = status_counts.get(status, 0) + 1

            has_js_challenge = "var _0x" in resp.text or "challenge" in resp.text[:300].lower()
            flag = " [RATE LIMITED / JS CHALLENGE]" if status == 429 or has_js_challenge else ""
            print(f"Burst Req #{i:02d}: Status {status} | Latency: {latency:.1f}ms | Payload: {len(resp.text)}B{flag}", flush=True)
        except Exception as e:
            err_name = type(e).__name__
            print(f"Burst Req #{i:02d}: ERROR ({err_name}): {e}", flush=True)
            status_counts["ERROR"] = status_counts.get("ERROR", 0) + 1

    _print_stats("Burst Mode (0.0s delay)", latencies, status_counts, total_requests)


def test_cooldown_recovery(session: requests.Session, cooldown_seconds: float = 16.0):
    print("\n" + "=" * 60, flush=True)
    print(f"BENCHMARK 2: AUTO-COOLDOWN RECOVERY ({cooldown_seconds}s sleep)", flush=True)
    print("Goal: Test if LinkedIn IP rate limit lifts after cooldown", flush=True)
    print("=" * 60, flush=True)

    print(f"Sleeping for {cooldown_seconds}s to let token bucket recover...", flush=True)
    time.sleep(cooldown_seconds)

    # Use fresh session like crawler does
    fresh_session = requests.Session(impersonate="chrome124")
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=Python&location=Vietnam&start=0"
    
    t0 = time.perf_counter()
    resp = fresh_session.get(url, headers=HEADERS_BASE, timeout=10)
    latency = (time.perf_counter() - t0) * 1000

    print(f"Post-Cooldown Req: Status {resp.status_code} | Latency: {latency:.1f}ms | Payload: {len(resp.text)}B", flush=True)
    if resp.status_code == 200:
        print("-> RECOVERY CONFIRMED: 429 lock successfully cleared!", flush=True)
    else:
        print(f"-> Lock still active (Status: {resp.status_code})", flush=True)


def test_polite_mode(session: requests.Session, total_requests: int = 3, delay: float = 2.5):
    print("\n" + "=" * 60, flush=True)
    print(f"BENCHMARK 3: POLITE MODE ({total_requests} requests, {delay}s delay)", flush=True)
    print("Goal: Verify stable throughput under safe delay interval", flush=True)
    print("=" * 60, flush=True)

    latencies = []
    status_counts = {}
    fresh_session = requests.Session(impersonate="chrome124")

    for i in range(1, total_requests + 1):
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=Python&location=Vietnam&start={(i-1)*10}"
        t0 = time.perf_counter()
        try:
            resp = fresh_session.get(url, headers=HEADERS_BASE, timeout=10)
            latency = (time.perf_counter() - t0) * 1000
            latencies.append(latency)
            status = resp.status_code
            status_counts[status] = status_counts.get(status, 0) + 1
            print(f"Polite Req #{i:02d}: Status {status} | Latency: {latency:.1f}ms | Payload: {len(resp.text)}B", flush=True)
        except Exception as e:
            err_name = type(e).__name__
            print(f"Polite Req #{i:02d}: ERROR ({err_name}): {e}", flush=True)
            status_counts["ERROR"] = status_counts.get("ERROR", 0) + 1

        if i < total_requests and delay > 0:
            time.sleep(delay)

    _print_stats(f"Polite Mode ({delay}s delay)", latencies, status_counts, total_requests)


if __name__ == "__main__":
    session = requests.Session(impersonate="chrome124")
    print("=" * 60, flush=True)
    print("STARTING LINKEDIN RATE LIMIT BENCHMARK SUITE", flush=True)
    print("=" * 60, flush=True)

    # 1. Burst Mode (Demonstrates 429 trigger threshold)
    test_burst_mode(session, total_requests=4)

    # 2. Cooldown Recovery (Demonstrates 16s recovery mechanism)
    test_cooldown_recovery(session, cooldown_seconds=16.0)

    # 3. Polite Mode (Demonstrates recommended production interval)
    test_polite_mode(session, total_requests=3, delay=2.5)

    print("\nBENCHMARK SUITE COMPLETED SUCCESSFULLY.", flush=True)
