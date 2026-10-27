from abc import ABC, abstractmethod
import json
import re
import time
from pathlib import Path
from typing import Optional

# pyrefly: ignore[missing-import]
from backend.config.log_config import get_logger

logger = get_logger(__name__)


RAW_DATA_ROOT = Path(__file__).resolve().parent.parent / "raw_data"
RAW_TEST_ROOT = Path(__file__).resolve().parent.parent / "raw_test"


class CrawlerRequestError(Exception):
    """
    Lỗi request do crawler con ném ra để CrawlerService đếm.
    - status_code: mã HTTP (4xx/5xx), hoặc None nếu là timeout/lỗi mạng.
    """

    def __init__(self, message: str, status_code: Optional[int] = None, url: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class CrawlerBase(ABC):
    file_path: Path = None
    # Nếu đặt (CrawlerService gán mỗi run): mọi response thô có raw_name sẽ được lưu nguyên bản vào đây
    raw_test_dir: Optional[Path] = None

    def save_raw_data(self, data: list[dict], run_id: str, file_name: str):
        """
        Append `data` (mỗi phần tử 1 dòng JSON) vào file_path/<run_id>/<file_name> (định dạng JSONL).
        Tự tạo thư mục run nếu chưa có. Ghi ngay để nếu crash thì không mất dữ liệu đã crawl.
        """
        if self.file_path is None:
            raise NotImplementedError(f"{type(self).__name__} chưa khai báo class attribute file_path")
        run_dir = Path(self.file_path) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / file_name, "a", encoding="utf-8") as f:
            for record in data:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _text(el) -> str:
        """Text của 1 phần tử BeautifulSoup, gộp khoảng trắng/xuống dòng thừa. Rỗng nếu el là None."""
        return " ".join(el.get_text(" ", strip=True).split()) if el is not None else ""

    @staticmethod
    def _clean_url(href: str) -> str:
        """Bỏ query string tracking (?ta_source=..., ?trk=..., ?lab_feature=...)."""
        return (href or "").split("?")[0].strip()

    # TẠM (đối chiếu): lưu response thô ra raw_test_dir. 
    def _dump_raw_test(self, label: str, url: str, raw: str) -> None:
        if self.raw_test_dir is None:
            return
        try:
            self.raw_test_dir.mkdir(parents=True, exist_ok=True)
            seq = len(list(self.raw_test_dir.iterdir())) + 1
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{label}_{url.split('?')[0].rstrip('/').rsplit('/', 1)[-1]}")[:120]
            ext = "json" if raw.lstrip()[:1] in ("{", "[") else "html"
            (self.raw_test_dir / f"{seq:03d}_{slug}.{ext}").write_text(raw, encoding="utf-8")
        except OSError as e:
            logger.warning("Không lưu được raw_test: %s", e)

    def _request(self, method: str, url: str, label: str, **kwargs) -> str:
        """
        Gửi 1 request qua self.session, đo thời gian, log, và kiểm tra mã HTTP.
        - method: "GET" / "POST"; **kwargs chuyển thẳng cho session.request (params, headers, json, data, timeout...).
        - label: tên mô tả dùng cho log/thông báo lỗi, ví dụ "ITViec search", "TopCV detail".
        Trả về resp.text khi HTTP 200; ném CrawlerRequestError nếu mã khác 200.
        Lỗi mạng/timeout do curl_cffi ném ra được giữ nguyên để CrawlerService ghi nhận.
        Không retry.
        """
        logger.debug("%s: %s %s", label, method, url)
        t0 = time.perf_counter()
        resp = self.session.request(method, url, **kwargs)
        elapsed = time.perf_counter() - t0

        if resp.status_code != 200:
            raise CrawlerRequestError(f"{label} HTTP {resp.status_code}", resp.status_code, url)
        logger.info("%s OK trong %.1fs: %s", label, elapsed, url)
        self._dump_raw_test(label, url, resp.text)
        return resp.text

    @abstractmethod
    def _create_session(self):
        """Khôi tạo và cấu hình session HTTP (curl_cffi/requests)."""
        pass

    @abstractmethod
    def search_jobs(self, page: int = 1, **kwargs) -> dict:
        """
        Lấy danh sách jobs của 1 trang (page đánh số từ 1).
        Gọi request rồi trả về kết quả của _extract_search: {"meta": {...}, "items": [...]}.
        Ném CrawlerRequestError (hoặc lỗi mạng) nếu request lỗi.
        """
        pass

    @abstractmethod
    def crawl_job_detail(self, job_url: str = None, job_id: str = None) -> dict:
        """
        Lấy thông tin chi tiết của 1 job theo job_url hoặc job_id.
        Gọi request rồi trả về kết quả của _extract_detail (dict đã cắt gọn).
        Ném CrawlerRequestError (hoặc lỗi mạng) nếu request lỗi.
        """
        pass

    @abstractmethod
    def _extract_search(self, raw: str) -> dict:
        """
        Cắt gọn response thô của trang search thành JSON: {"meta": {...}, "items": [...]}.
        - meta: thông tin cấp trang (tổng số job, tổng số trang, ...), nếu nền tảng có.
        - items: mỗi phần tử là 1 job card, gồm các trường có ích đã lấy sẵn từ nguồn.
        Chỉ giữ nguyên thông tin có ích (giữ text/HTML gốc), CHƯA ánh xạ sang trường chuẩn.
        Nguồn JSON: giữ nguyên. Nguồn HTML: bỏ khối thừa và format lại thành JSON.
        """
        pass

    @abstractmethod
    def _extract_detail(self, raw: str) -> dict:
        """
        Cắt gọn response thô của trang chi tiết job thành 1 dict JSON.
        Cùng nguyên tắc với _extract_search: giữ thông tin có ích, chưa ánh xạ sang trường chuẩn.
        """
        pass

    @abstractmethod
    def get_job_refs(self, search_result: dict) -> list[dict]:
        """
        Từ kết quả search_jobs/_extract_search ({"meta", "items"}), trích tối thiểu danh sách
        [{"job_id": ..., "job_url": ...}] (giá trị nào nền tảng không có thì để None)
        để CrawlerService đếm job unique và gọi crawl_job_detail.
        """
        pass


