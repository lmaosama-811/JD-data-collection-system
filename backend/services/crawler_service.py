import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# pyrefly: ignore[missing-import]
from backend.config.log_config import get_logger
from backend.crawler.crawler_base import CrawlerBase
from backend.crawler.itviec_crawler import itviec_crawler
from backend.crawler.linkedIn_crawler import linkedin_crawler
from backend.crawler.nodeflair_crawler import nodeflair_crawler
from backend.crawler.topcv_crawler import topcv_crawler
from backend.crawler.vietnamworks_crawler import vietnamworks_crawler

logger = get_logger(__name__)


class CrawlerService:
    # Số trang list liên tiếp bị lỗi thì dừng giai đoạn lấy danh sách
    MAX_CONSECUTIVE_LIST_FAILURES = 3
    # Số lỗi tối đa lưu trong manifest (tránh manifest phình khi lỗi hàng loạt)
    MAX_ERRORS_IN_MANIFEST = 20

    def __init__(self):
        self.crawlers: dict[str, CrawlerBase] = {
            "topcv": topcv_crawler,
            "itviec": itviec_crawler,
            "vietnamworks": vietnamworks_crawler,
            "nodeflair": nodeflair_crawler,
            "linkedin": linkedin_crawler,
        }

    def crawl_jobs(self, platform: str, max_pages: int = 1, limit_jobs: int = None) -> dict:
        """
        1. Tạo run_id, ghi manifest.json (status=running, completed_at=null)
        2. Chạy search_jobs từng trang -> ghi job_lists.jsonl
        3. Chạy crawl_job_detail từng job -> ghi job_details.jsonl
        4. Tổng hợp và ghi lại manifest.json lần cuối.
        Biến đếm là biến local; crawler con ném exception khi request lỗi, service bắt và đếm.
        """
        if platform not in self.crawlers:
            raise ValueError(f"Platform không hợp lệ: {platform}. Hỗ trợ: {list(self.crawlers)}")
        crawler = self.crawlers[platform]
        delay = getattr(crawler, "DELAY_PER_REQUESTS", 0) or 0

        started_at = datetime.now(timezone.utc)
        run_id = self._create_crawl_run_id(started_at)
        logger.info("[%s] Bắt đầu run %s (max_pages=%s, limit_jobs=%s, delay=%ss)", platform, run_id, max_pages, limit_jobs, delay)

        list_total = list_success = list_failed = 0
        detail_success = detail_failed = 0

        manifest = {
            "run_id": run_id,
            "platform": platform,
            "crawl_date": started_at.strftime("%Y-%m-%d"),
            "started_at": self._iso(started_at),
            "completed_at": None,
            "status": "running",
            "job_list_stage": {
                "requests_total": 0,
                "requests_success": 0,
                "requests_failed": 0,
                "job_ids_collected": 0,
            },
            "job_detail_stage": {"jobs_success": 0, "jobs_failed": 0},
            "errors": [],
        }
        # Ghi ngay từ đầu: nếu crash giữa chừng thì manifest vẫn ở trạng thái "running"
        self._save_manifest(crawler, run_id, manifest)

        # ---------------- Giai đoạn 1: danh sách job ----------------
        job_refs: dict[str, dict] = {}  # key = job_id hoặc job_url -> {"job_id", "job_url"}
        consecutive_failures = 0

        for page in range(1, max_pages + 1):
            if page > 1 and delay:
                time.sleep(delay)

            list_total += 1
            try:
                result = crawler.search_jobs(page=page)
            except Exception as e:
                list_failed += 1
                consecutive_failures += 1
                self._record_error(manifest, platform, "list", f"page={page}", e)
                if consecutive_failures >= self.MAX_CONSECUTIVE_LIST_FAILURES:
                    logger.error("[%s] %d trang list liên tiếp lỗi, dừng giai đoạn list", platform, consecutive_failures)
                    break
                continue

            list_success += 1
            consecutive_failures = 0
            refs_in_page = crawler.get_job_refs(result)
            if not refs_in_page:
                logger.info("[%s] Trang %d không còn job, dừng giai đoạn list", platform, page)
                break  # hết dữ liệu

            crawler.save_raw_data(
                [{
                    "page": page,
                    "fetched_at": self._iso(datetime.now(timezone.utc)),
                    "meta": result.get("meta"),
                    "items": result.get("items"),
                }],
                run_id,
                "job_lists.jsonl",
            )
            for ref in refs_in_page:
                key = ref.get("job_id") or ref.get("job_url")
                if key and key not in job_refs:
                    job_refs[key] = ref

        manifest["job_list_stage"] = {
            "requests_total": list_total,
            "requests_success": list_success,
            "requests_failed": list_failed,
            "job_ids_collected": len(job_refs),
        }
        self._save_manifest(crawler, run_id, manifest)
        logger.info("[%s] Giai đoạn list xong: %d/%d request OK, thu được %d job unique", platform, list_success, list_total, len(job_refs))

        # ---------------- Giai đoạn 2: chi tiết job ----------------
        refs = list(job_refs.values())
        if limit_jobs:
            refs = refs[:limit_jobs]

        total_refs = len(refs)
        logger.info("[%s] Bắt đầu giai đoạn detail: %d job", platform, total_refs)

        for idx, ref in enumerate(refs, 1):
            if delay:
                time.sleep(delay)
            try:
                detail = crawler.crawl_job_detail(job_url=ref.get("job_url"), job_id=ref.get("job_id"))
            except Exception as e:
                detail_failed += 1
                self._record_error(manifest, platform, "detail", ref.get("job_id") or ref.get("job_url"), e)
                continue

            detail_success += 1
            logger.debug("[%s] Detail %d/%d OK: %s", platform, idx, total_refs, ref.get("job_id") or ref.get("job_url"))
            crawler.save_raw_data(
                [{
                    "job_id": ref.get("job_id"),
                    "job_url": ref.get("job_url"),
                    "fetched_at": self._iso(datetime.now(timezone.utc)),
                    "data": detail,
                }],
                run_id,
                "job_details.jsonl",
            )

        # ---------------- Tổng hợp ----------------
        total_success = list_success + detail_success
        total_failed = list_failed + detail_failed
        if total_success == 0:
            status = "failed"
        elif total_failed > 0:
            status = "partial_success"
        else:
            status = "success"

        manifest["job_detail_stage"] = {"jobs_success": detail_success, "jobs_failed": detail_failed}
        manifest["status"] = status
        manifest["completed_at"] = self._iso(datetime.now(timezone.utc))
        self._save_manifest(crawler, run_id, manifest)
        log = logger.info if status == "success" else logger.warning
        log("[%s] Kết thúc run %s: status=%s, list %d/%d OK, detail %d OK / %d lỗi",
            platform, run_id, status, list_success, list_total, detail_success, detail_failed)
        return manifest

    def _record_error(self, manifest: dict, platform: str, stage: str, target, exc: Exception):
        """Log lỗi ra console và lưu vào manifest["errors"] (giới hạn MAX_ERRORS_IN_MANIFEST)."""
        message = f"{type(exc).__name__}: {exc}"
        logger.warning("[%s] %s lỗi (%s): %s", platform, stage, target, message)
        if len(manifest["errors"]) < self.MAX_ERRORS_IN_MANIFEST:
            manifest["errors"].append({
                "stage": stage,
                "target": target,
                "status_code": getattr(exc, "status_code", None),
                "error": message[:500],
            })

    def _create_crawl_run_id(self, now: datetime = None) -> str:
        """Dạng 20261020T020000Z-run_a1b2c3 (cũng là tên thư mục của run)."""
        now = now or datetime.now(timezone.utc)
        return f"{now.strftime('%Y%m%dT%H%M%SZ')}-run_{uuid.uuid4().hex[:6]}"

    def _save_manifest(self, crawler: CrawlerBase, run_id: str, manifest: dict):
        run_dir = Path(crawler.file_path) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _iso(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
