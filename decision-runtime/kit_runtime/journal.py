"""Durable checkpoint replacement: retain the last complete receipt on write failure."""
import json
import os
from pathlib import Path
import tempfile


def write_json(path, data):
    path = Path(path)
    # Serialize before touching the old journal or creating a temporary file.
    payload = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=path.parent, prefix='.' + path.name + '-',
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
