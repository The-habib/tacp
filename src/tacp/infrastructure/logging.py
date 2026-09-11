import json
import logging
import re
from typing import Any, Dict

SECRET_PATTERNS = [
    re.compile(r"-----(BEGIN|END) [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9_]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{82,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{32,}"),
    re.compile(r"ya29\.[A-Za-z0-9_\-]+"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"(password|secret|token|api_key)=([^\s&]+)", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


# Compatibility alias
redact_string = redact_secrets


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for k, v in data.items():
        if any(sec in k.lower() for sec in ["token", "secret", "password", "key", "auth"]):
            clean[k] = "[REDACTED]"
        elif isinstance(v, str):
            clean[k] = redact_secrets(v)
        elif isinstance(v, dict):
            clean[k] = redact_dict(v)
        elif isinstance(v, list):
            clean[k] = [
                redact_dict(item)
                if isinstance(item, dict)
                else (redact_secrets(item) if isinstance(item, str) else item)
                for item in v
            ]
        else:
            clean[k] = v
    return clean


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "component": record.name,
            "message": redact_secrets(record.getMessage()),
        }
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        return json.dumps(payload)
