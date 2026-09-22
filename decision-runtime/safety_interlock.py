"""All unattended entry points must fail closed after a native safety exit.

This module deliberately has no clear/unlock API. The owner acknowledges in Kit UI.
"""
import json
from pathlib import Path

def require_unlocked(root, status=None):
    path = Path(root) / 'safety-hold.json'
    if path.exists():
        try:
            record = json.loads(path.read_text())
            if not isinstance(record.get('active'), bool):
                raise ValueError('Invalid safety record')
        except (OSError, ValueError, AttributeError) as error:
            raise RuntimeError('Safety record unreadable; await manual in-game confirmation') from error
        if record['active']:
            raise RuntimeError('Safety lock active; do not reconnect or resume automatically')
    if (status or {}).get('safety_hold', {}).get('active'):
        raise RuntimeError('Native safety lock active; await manual in-game confirmation')
