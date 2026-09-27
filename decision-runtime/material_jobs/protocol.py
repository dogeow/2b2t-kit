"""File protocol shared with the native Kit job launcher; no game or model imports."""
import hashlib
import json
import math
import re

class JobPaused(RuntimeError):
    pass


class JobCancelled(JobPaused):
    pass


class JobBlocked(RuntimeError):
    pass


def validate_request(value):
    if not isinstance(value, dict) or value.get('schema') != 1:
        raise ValueError('Expected material job request schema 1')
    if not isinstance(value.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value['id']):
        raise ValueError('Invalid material job id')
    if value.get('mode') not in ('item', 'projection'):
        raise ValueError('Material job mode must be item or projection')
    if not isinstance(value.get('targets', {}), dict):
        raise ValueError('Targets must map item IDs to counts')
    targets = {}
    for item, count in value.get('targets', {}).items():
        if (not isinstance(item, str) or not re.fullmatch(r'minecraft:[a-z0-9_./-]+', item)
                or type(count) is not int or not 0 <= count <= 1_000_000):
            raise ValueError('Invalid vanilla material target')
        if count:
            targets[item] = count
    if value['mode'] == 'item' and not targets:
        raise ValueError('Item jobs need a positive target')
    if len(targets) > 256:
        raise ValueError('Too many target materials')
    if value['mode'] == 'projection' and not value.get('projection_key'):
        raise ValueError('Projection jobs need the selected placement key')
    context = value.get('context', {})
    if any(not isinstance(context.get(field), str) or not context[field]
           for field in ('server', 'dimension', 'world_session')):
        raise ValueError('A server, dimension and world session are required')
    if type(context.get('expected_revision')) is not int or context['expected_revision'] < 0:
        raise ValueError('Expected control revision is required')
    start = context.get('start_pos')
    if (not isinstance(start, list) or len(start) != 3
            or any(type(n) not in (int, float) or not math.isfinite(n) for n in start)):
        raise ValueError('The starting position must be a finite XYZ vector')
    if type(value.get('created_at')) is not int or value['created_at'] <= 0:
        raise ValueError('Request creation time is required')
    return {**value, 'targets': dict(targets), 'context': dict(context)}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def server_key(server):
    return str(server).lower().removesuffix(':25565')
