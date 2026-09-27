"""Bounded read-only recovery of native removal receipts, never pickup proof.

Only retained material-worker event logs are read. A returned removal still
needs the caller's current model hash and exact AIR observation. Drop UUIDs
are hints from later pickup requests, never evidence that an item was received.
"""
from copy import deepcopy
from decimal import Decimal
import heapq
import json
import math
import os
from pathlib import Path
import stat
import uuid


MAX_EVENT_FILES = 128
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_EVENT_LINES = 20000
MAX_LINE_BYTES = 64 * 1024
DROP_HINT_SECONDS = 60


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _position(value, *, integers=False):
    return (isinstance(value, list) and len(value) == 3
            and all(type(n) is int if integers else _number(n) for n in value))


def _newest_logs(root):
    def candidates():
        for path in (Path(root) / 'material-jobs').glob('*/control-*/events.jsonl'):
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                yield info.st_mtime_ns, str(path), info
    selected = heapq.nlargest(MAX_EVENT_FILES, candidates(), key=lambda row: row[:2])
    if sum(info.st_size for _, _, info in selected) > MAX_TOTAL_BYTES:
        return None
    return [(Path(name), info) for _, name, info in selected]


def _invalid_constant(value):
    raise ValueError('Non-finite JSON number: ' + value)


def _read_events(path, expected_stat):
    """Reject incomplete, oversized, changing or malformed evidence files."""
    if expected_stat.st_size > MAX_FILE_BYTES:
        return None
    events = []
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                expected_stat.st_dev, expected_stat.st_ino, expected_stat.st_size, expected_stat.st_mtime_ns):
            return None
        for index in range(MAX_EVENT_LINES + 1):
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if index == MAX_EVENT_LINES or len(line) > MAX_LINE_BYTES:
                return None
            if not line.strip():
                continue
            event = json.loads(line, parse_constant=_invalid_constant)
            if not isinstance(event, dict):
                return None
            events.append((index, event))
        final = os.fstat(stream.fileno())
    # Do not trust a scan that raced appending or replacing the log.
    current = path.stat()
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return events if identity(final) == identity(expected_stat) == identity(current) else None


def _same_receipt(events):
    """Exact duplicates are harmless; inconsistent same-ID receipts are not."""
    return all(event == events[0] for event in events[1:])


def _uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False


def find_removal_receipt(automation_root, pending, portal_block):
    """Return {native_event, owned_drop_ids}, or None when proof is uncertain.

    Event time is Unix seconds; pending.created_at_ns is Unix nanoseconds. Scan
    at most the 128 newest ``material-jobs/*/control-*/events.jsonl`` files.
    Bounds/read errors/malformed logs fail closed, without modifying any file.
    The original pending world is intentionally used across later reconnects.
    """
    if not isinstance(pending, dict) or pending.get('kind') != 'open_block' or not isinstance(portal_block, dict):
        return None
    pos, expected, item = (portal_block.get(key) for key in ('pos', 'expected', 'item'))
    created = pending.get('created_at_ns')
    world = pending.get('world_session')
    records = pending.get('request_records')
    if (not _position(pos, integers=True) or not isinstance(expected, str) or not expected.startswith('Block{minecraft:')
            or not isinstance(item, str) or not item.startswith('minecraft:')
            or type(created) is not int or created <= 0 or not isinstance(world, str) or not world
            or not isinstance(records, list)):
        return None
    ids = {row['request_id'] for row in records if isinstance(row, dict)
           and isinstance(row.get('request_id'), str) and row['request_id']}
    if not ids:
        return None
    intent = pending.get('data', {})
    if not isinstance(intent, dict) or ('pos' in intent and intent['pos'] != pos) or ('item' in intent and intent['item'] != item):
        return None
    matched_ids = {}
    later_pickups = {}
    try:
        files = _newest_logs(automation_root)
        if files is None:
            return None
        for path, info in files:
            events = _read_events(path, info)
            if events is None:
                return None
            for index, event in events:
                if event.get('request_id') in ids:
                    matched_ids.setdefault(event['request_id'], []).append((path, index, event))
                params = event.get('params')
                if (event.get('op') == 'collect_item' and event.get('world_session') == world
                        and isinstance(params, dict) and params.get('expected_item') == item
                        and _position(event.get('pos')) and math.dist(event['pos'], pos) <= 8
                        and _uuid(params.get('expected_uuid')) and _number(event.get('time'))):
                    later_pickups.setdefault(path, []).append((index, event))
    except (OSError, ValueError, TypeError, OverflowError):
        return None
    candidates = []
    for entries in matched_ids.values():
        if not _same_receipt([event for _, _, event in entries]):
            return None
        path, index, event = entries[0]
        params = event.get('params')
        if (event.get('op') == 'mine_block' and event.get('phase') == 'done'
                and event.get('world_session') == world and isinstance(params, dict)
                and _position(params.get('pos'), integers=True) and params['pos'] == pos
                and params.get('expected_state') == expected and _number(event.get('time'))
                and Decimal(str(event['time'])) * 1_000_000_000 >= created):
            candidates.append(entries)
    # Several different successful request IDs are ambiguous, not two receipts
    # to merge into a supposed single removal.
    if len(candidates) != 1:
        return None
    entries = candidates[0]
    native_event = entries[0][2]
    task = native_event['params'].get('task_session')
    hint_ids = set()
    if isinstance(task, str) and task:
        for path, removal_index, removal in entries:
            for index, event in later_pickups.get(path, []):
                if (index > removal_index and event['params'].get('task_session') == task
                        and 0 <= event['time'] - removal['time'] <= DROP_HINT_SECONDS):
                    hint_ids.add(event['params']['expected_uuid'])
    return {'native_event': deepcopy(native_event), 'owned_drop_ids': sorted(hint_ids)}
