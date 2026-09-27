"""Bounded, redacted diagnostic events; authoritative transaction journals stay separate."""
from __future__ import annotations

import fcntl
import json
from itertools import islice
import math
import re
import time
from pathlib import Path
from typing import Any

_SECRET_KEYS = {"authorization", "api_key", "apikey", "access_token", "refresh_token",
                "cookie", "password", "secret", "client_secret"}
_KEY_PATTERN = re.compile(r"\bapikey_[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"\b(Bearer\s+)[^\s\"'<>;,]+", re.IGNORECASE)


def redact(value: Any, depth: int = 0) -> Any:
    if isinstance(value, dict):
        if depth >= 5:
            return "[nested data omitted]"
        result = {}
        for key, item in islice(value.items(), 32):
            name = _KEY_PATTERN.sub("[redacted]", str(key))
            result[name] = "[redacted]" if name.lower().replace("-", "_") in _SECRET_KEYS else redact(item, depth + 1)
        if len(value) > 32:
            result["omitted_fields"] = len(value) - 32
        return result
    if isinstance(value, (list, tuple)):
        if depth >= 5:
            return "[nested data omitted]"
        result = [redact(item, depth + 1) for item in value[:16]]
        if len(value) > 16:
            result.append({"omitted_items": len(value) - 16})
        return result
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raw = str(value)
    text = _BEARER_PATTERN.sub(r"\1[redacted]", _KEY_PATTERN.sub("[redacted]", raw[:4096]))
    return text[:500] + ("…" if len(text) > 500 or len(raw) > 4096 else "")


class EventLog:
    """Small diagnostic history with a fixed disk budget and atomic rotation under a lock."""
    def __init__(self, path: Path, max_bytes: int = 2_000_000, backups: int = 3):
        if max_bytes < 256 or not 1 <= backups <= 8:
            raise ValueError("Invalid diagnostic log budget")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backups = backups

    def emit(self, kind: str, **fields: Any) -> None:
        row = redact({"time": time.time(), "kind": kind, **fields})
        encoded = (json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n").encode("utf8")
        if len(encoded) > self.max_bytes:
            row = {"time": time.time(), "kind": kind, "diagnostic_fields_omitted": True}
            encoded = (json.dumps(row) + "\n").encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.exists() and self.path.stat().st_size + len(encoded) > self.max_bytes:
                for index in range(self.backups, 0, -1):
                    older = self.path.with_name(f"{self.path.stem}.{index}{self.path.suffix}")
                    source = self.path if index == 1 else self.path.with_name(f"{self.path.stem}.{index-1}{self.path.suffix}")
                    if source.exists():
                        source.replace(older)
            with self.path.open("ab") as stream:
                stream.write(encoded)


def tail_events(path: Path, limit: int = 200, max_bytes: int = 262_144) -> list[dict]:
    """Read only a bounded tail, including files that ended with a partial last line."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open("rb") as stream:
        size = path.stat().st_size
        start = max(0, size - max_bytes)
        stream.seek(start)
        lines = stream.read(max_bytes).decode("utf8", errors="replace").splitlines()
    if start and lines:
        lines = lines[1:]
    result = []
    for line in lines[-limit:]:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                result.append(item)
        except ValueError:
            pass
    return result
