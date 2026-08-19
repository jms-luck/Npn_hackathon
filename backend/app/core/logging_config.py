import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from backend.app.core.config import settings


SERVICES = ("auth", "admin", "jobs", "candidate", "resumes", "matching", "interviews", "bulk", "companies", "ai", "blob", "neo4j", "system", "audit")
RESERVED = {"name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process", "taskName"}
_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update({key: value for key, value in record.__dict__.items() if key not in RESERVED and not key.startswith("_")})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = JsonFormatter()
    for service in SERVICES:
        logger = logging.getLogger(f"hireai.{service}")
        logger.setLevel(level)
        logger.propagate = False
        file_handler = RotatingFileHandler(log_dir / f"{service}.log", maxBytes=settings.log_max_bytes, backupCount=settings.log_backup_count, encoding="utf-8")
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.handlers.clear()
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
    _configured = True


def service_logger(service: str) -> logging.Logger:
    return logging.getLogger(f"hireai.{service if service in SERVICES else 'system'}")


def audit_event(service: str, action: str, **fields: Any) -> None:
    service_logger("audit").info("audit_event", extra={"service": service, "action": action, **fields})
