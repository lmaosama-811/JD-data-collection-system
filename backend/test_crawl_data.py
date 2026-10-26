"""
Script test tạm: chạy CrawlerService.crawl_jobs cho từng nền tảng để kiểm tra khả năng cào và lưu dữ liệu.
Dữ liệu đã cắt gọn (JSON) được lưu vào backend/raw_data/<platform>/<run_id>/
(manifest.json, job_lists.jsonl, job_details.jsonl).

Chạy từ thư mục gốc dự án:
    python -m backend.test_crawl_data                       # cả 5 nền tảng, 1 trang search, tối đa 5 job detail
    python -m backend.test_crawl_data itviec nodeflair      # chỉ một số nền tảng
    python -m backend.test_crawl_data itviec --pages 2 --limit 10
    python -m backend.test_crawl_data topcv --limit 0       # limit 0 = lấy hết job của các trang đã crawl
"""
import argparse
import json
from pathlib import Path

from backend.services.crawler_service import CrawlerService

PLATFORMS = ["topcv", "itviec", "vietnamworks", "nodeflair", "linkedin"]


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f)


def test_platform(service: CrawlerService, platform: str, pages: int, limit: int):
    print(f"\n===== {platform.upper()} =====")
    try:
        manifest = service.crawl_jobs(platform, max_pages=pages, limit_jobs=limit or None)
    except Exception as e:
        print(f"[!] crawl_jobs lỗi: {type(e).__name__}: {e}")
        return

    run_dir = Path(service.crawlers[platform].file_path) / manifest["run_id"]
    print(f"[=] run_id : {manifest['run_id']}")
    print(f"[=] status : {manifest['status']}")
    print(f"[=] list   : {json.dumps(manifest['job_list_stage'], ensure_ascii=False)}")
    print(f"[=] detail : {json.dumps(manifest['job_detail_stage'], ensure_ascii=False)}")
    for name in ("manifest.json", "job_lists.jsonl", "job_details.jsonl"):
        p = run_dir / name
        size = p.stat().st_size if p.exists() else 0
        lines = f", {_count_lines(p)} dòng" if name.endswith(".jsonl") else ""
        print(f"    - {name}: {size} bytes{lines}")
    print(f"[=] thư mục: {run_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test cào và lưu dữ liệu đã cắt gọn")
    parser.add_argument("platforms", nargs="*", choices=PLATFORMS, help="Mặc định: cả 5 nền tảng")
    parser.add_argument("--pages", type=int, default=1, help="Số trang search mỗi nền tảng (mặc định 1)")
    parser.add_argument("--limit", type=int, default=5, help="Giới hạn số job detail mỗi nền tảng (mặc định 5, 0 = không giới hạn)")
    args = parser.parse_args()

    service = CrawlerService()
    for p in (args.platforms or PLATFORMS):
        test_platform(service, p, pages=args.pages, limit=args.limit)
