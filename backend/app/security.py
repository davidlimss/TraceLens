import threading
import time
import unicodedata
import uuid
from collections import defaultdict
from pathlib import Path

import redis

from app.parsers.detector import FormatDetectionError, detect_format

ALLOWED_MIME_TYPES = {
    "text/plain", "text/csv", "application/csv", "application/json", "application/x-ndjson", "application/jsonl", "application/octet-stream",
}
ALLOWED_EXTENSIONS = {".log", ".json", ".jsonl", ".ndjson", ".csv"}
ALLOWED_EXTENSIONLESS_NAMES = {"syslog", "auth", "access_log"}


class UploadValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def validate_size(current_size: int, chunk_size: int, maximum_size: int) -> int:
    new_size = current_size + chunk_size
    if new_size > maximum_size:
        raise UploadValidationError(f"file exceeds maximum size of {maximum_size} bytes", 413)
    return new_size


def validate_filename(filename: str | None) -> str:
    if not filename:
        raise UploadValidationError("filename is required")
    normalized = unicodedata.normalize("NFKC", filename).strip()
    if not normalized or "\x00" in normalized or "/" in normalized or "\\" in normalized:
        raise UploadValidationError("unsafe filename or path traversal detected")
    if normalized in {".", ".."} or Path(normalized).name != normalized:
        raise UploadValidationError("unsafe filename or path traversal detected")
    suffix = Path(normalized).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS and normalized.lower() not in ALLOWED_EXTENSIONLESS_NAMES:
        raise UploadValidationError("unsupported file extension", status_code=415)
    return normalized


def validate_mime_type(content_type: str | None) -> str:
    normalized = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if normalized not in ALLOWED_MIME_TYPES:
        raise UploadValidationError("unsupported MIME type", status_code=415)
    return normalized


def validate_sample_and_detect(sample: bytes) -> str:
    if not sample:
        raise UploadValidationError("uploaded file is empty")
    try:
        text = sample.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise UploadValidationError("log file must be valid UTF-8") from exc
    return validate_text_and_detect(text)


def validate_text_and_detect(text: str) -> str:
    if not text:
        raise UploadValidationError("uploaded file is empty")
    try:
        return detect_format(text.splitlines())
    except FormatDetectionError as exc:
        raise UploadValidationError("content does not match a supported log format", status_code=415) from exc


def safe_evidence_path(storage_dir: Path, evidence_id: uuid.UUID) -> Path:
    base = storage_dir.resolve()
    target = (base / str(evidence_id)).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise UploadValidationError("evidence path escapes storage directory") from exc
    return target


class RateLimitExceeded(RuntimeError):
    pass


class FixedWindowRateLimiter:
    def __init__(self, redis_url: str | None = None):
        self.redis = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=0.25,
                                          socket_timeout=0.25) if redis_url else None
        self._fallback: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int, now: int | None = None) -> int:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("rate limit and window must be positive")
        bucket = int((now if now is not None else time.time()) // window_seconds)
        redis_key = f"rate-limit:{key}:{bucket}"
        if self.redis is not None:
            try:
                with self.redis.pipeline() as pipe:
                    pipe.incr(redis_key)
                    pipe.expire(redis_key, window_seconds + 1)
                    count, _ = pipe.execute()
                if int(count) > limit:
                    raise RateLimitExceeded("rate limit exceeded")
                return int(count)
            except RateLimitExceeded:
                raise
            except redis.RedisError:
                pass
        with self._lock:
            existing_bucket, count = self._fallback[key]
            count = count + 1 if existing_bucket == bucket else 1
            self._fallback[key] = (bucket, count)
        if count > limit:
            raise RateLimitExceeded("rate limit exceeded")
        return count
