"""
Cấu hình logging tập trung cho toàn dự án.

Cách dùng ở mỗi module:
    from backend.config.log_config import get_logger
    logger = get_logger(__name__)

- Console: mức INFO trở lên.
- File backend/logs/app.log: mức DEBUG trở lên, tự xoay vòng (5 MB x 3 file).
- setup_logging() chỉ cấu hình 1 lần (gọi nhiều lần cũng không bị nhân đôi handler).
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Đổi mức log console bằng biến môi trường LOG_LEVEL (mặc định INFO)
CONSOLE_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

_configured = False


def setup_logging() -> None:
    """Gắn handler console + file vào root logger (chỉ chạy 1 lần)."""
    global _configured
    if _configured:
        return

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    console = logging.StreamHandler()
    console.setLevel(CONSOLE_LEVEL)
    console.setFormatter(formatter)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)

    # Thư viện ngoài quá ồn ở DEBUG
    for noisy in ("urllib3", "asyncio", "playwright", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Trả về logger đã đảm bảo logging được cấu hình."""
    setup_logging()
    return logging.getLogger(name)
