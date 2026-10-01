"""Small allowlist-based redaction for local evidence and learned transactions."""
from __future__ import annotations
import json
from pathlib import Path

SENSITIVE_KEYS=frozenset({'snow_expedition_token','token'})
REDACTED='<redacted>'


def sanitize(value):
    if isinstance(value,dict):
        return {key:(REDACTED if key in SENSITIVE_KEYS else sanitize(child))
                for key,child in value.items()}
    if isinstance(value,list):return [sanitize(child) for child in value]
    if isinstance(value,tuple):return [sanitize(child) for child in value]
    return value


def scrub_confirmed_json(path,request_id,world_session):
    """Atomically redact one exact confirmed mailbox document, never a foreign action."""
    path=Path(path)
    if not path.exists():return False
    value=json.loads(path.read_text())
    if (not isinstance(value,dict) or value.get('id')!=request_id
            or value.get('world_session')!=world_session):return False
    safe=sanitize(value)
    if safe==value:return True
    temporary=path.with_name(path.name+'.scrub.tmp')
    temporary.write_text(json.dumps(safe,ensure_ascii=False,separators=(',',':')))
    temporary.replace(path)
    return True
