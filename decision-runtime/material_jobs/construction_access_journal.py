"""Durable temporary-access receipts; never dispatches, reconnects or replays.

The caller owns fresh exact probes, interpretation of inventory/drop evidence,
and all game actions. A journal record is never evidence of game success.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from kit_runtime.journal import write_json

_SCOPE_FIELDS = ('server', 'dimension', 'placement_key', 'model_hash')
_AIR = {'Block{minecraft:air}', 'Block{minecraft:cave_air}', 'Block{minecraft:void_air}'}
_BLOCK = re.compile(r'Block\{(minecraft:[a-z0-9_]+)\}(?:\[[^\]]+\])?')
_SECRET_KEYS = {'token', 'access_token', 'api_key', 'apikey', 'authorization',
                'password', 'secret', 'private_key', 'cookie'}
_CONTAINERS = {'chest', 'trapped_chest', 'ender_chest', 'barrel', 'hopper',
               'dispenser', 'dropper', 'furnace', 'blast_furnace', 'smoker',
               'brewing_stand', 'crafter', 'decorated_pot', 'lectern',
               'chiseled_bookshelf', 'beehive', 'bee_nest', 'jukebox'}


class AccessJournalError(ValueError):
    """A transition or its evidence cannot safely be accepted."""


def _json_copy(value):
    def check(node):
        if isinstance(node, dict):
            for key, child in node.items():
                if not isinstance(key, str):
                    raise AccessJournalError('Journal keys must be strings')
                if key.lower() in _SECRET_KEYS:
                    raise AccessJournalError('Credentials must not be stored in access journals')
                check(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                check(child)
    check(value)
    return json.loads(json.dumps(value, allow_nan=False))


def _scope(scope):
    if not isinstance(scope, dict) or any(
            not isinstance(scope.get(key), str) or not scope[key].strip()
            for key in _SCOPE_FIELDS):
        raise AccessJournalError('Scope requires server, dimension, placement_key and model_hash')
    return {key: scope[key] for key in _SCOPE_FIELDS}


def _position(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3 or any(type(n) is not int for n in value):
        raise AccessJournalError('Portal positions must be integer XYZ coordinates')
    return tuple(value)


def _safe_state(state):
    if not isinstance(state, str):
        return False
    match = _BLOCK.fullmatch(state)
    if not match:
        return False
    block = match[1].removeprefix('minecraft:')
    return (block not in _CONTAINERS and not block.endswith('shulker_box')
            and block not in {'water', 'lava', 'bubble_column'}
            and 'waterlogged=true' not in state)


def _plan(value):
    value = _json_copy(value)
    if not isinstance(value, dict) or not isinstance(value.get('blocks'), list) or len(value['blocks']) != 2:
        raise AccessJournalError('A two-block access plan is required for a new transaction')
    positions = []
    for block in value['blocks']:
        if not isinstance(block, dict):
            raise AccessJournalError('Invalid portal block')
        positions.append(_position(block.get('pos')))
        if not _safe_state(block.get('expected')) or block['expected'] in _AIR:
            raise AccessJournalError('Portal originals must be known non-fluid, non-container blocks')
        if not isinstance(block.get('item'), str) or not re.fullmatch(r'minecraft:[a-z0-9_]+', block['item']):
            raise AccessJournalError('Portal restoration item is required')
    if len(set(positions)) != 2:
        raise AccessJournalError('Portal positions must be distinct')
    for name in ('outside', 'inside'):
        point = value.get(name)
        if not isinstance(point, list) or len(point) != 3 or any(type(n) not in (int, float) for n in point):
            raise AccessJournalError('Plan requires outside and inside XYZ standing positions')
    return value


def journal_path(index_dir, scope, transaction_id=None):
    """Stable across world sessions; a fresh transaction uses a new explicit ID."""
    scope = _scope(scope)
    digest = hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    label = '-'.join(re.sub(r'[^A-Za-z0-9_-]', '_', scope[key])[:32]
                     for key in ('server', 'dimension', 'placement_key'))
    model = re.sub(r'[^A-Za-z0-9_-]', '_', scope['model_hash'])[:64]
    path = Path(index_dir) / (label + '-' + digest[:16]) / (model + '-' + digest[16:32])
    if transaction_id is not None:
        if not isinstance(transaction_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', transaction_id):
            raise AccessJournalError('Invalid transaction ID')
        path /= transaction_id
    return path / 'access.json'


class AccessJournal:
    """Immutable-scope transaction with write-ahead intent and detached views.

    observations = {fresh: True, exact: True, world_session: str, blocks: [...]}
    Each block row needs pos, state, fluid=False and container=False. A list of
    rows carrying their own fresh/exact/world_session metadata is also accepted.
    Confirmation and restored checkpoints require nonempty inventory or drops
    evidence, whose content and meaning must be checked by the caller.
    """

    def __init__(self, path, scope, plan=None):
        self.path = Path(path)
        self.scope = _scope(scope)
        self._validated_session = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked():
            if self.path.exists():
                self._data = self._read()
                if plan is not None and _plan(plan) != self._data['plan']:
                    raise AccessJournalError('Existing transaction plan cannot be replaced')
            else:
                data = {'schema': 1, 'transaction_id': uuid.uuid4().hex,
                        'scope': self.scope, 'plan': _plan(plan), 'stage': 'planned',
                        'revision': 0, 'created_at_ns': time.time_ns(),
                        'pending': None, 'operations': [], 'checkpoints': [], 'epochs': []}
                write_json(self.path, data)
                self._data = data

    @property
    def data(self):
        return deepcopy(self._data)

    @property
    def pending(self):
        return deepcopy(self._data['pending'])

    @property
    def restored(self):
        return self._data['stage'] == 'restored'

    @contextmanager
    def _locked(self):
        with self.path.with_name(self.path.name + '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self):
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('schema') != 1 or data.get('scope') != self.scope:
            raise AccessJournalError('Journal scope/schema mismatch; existing record preserved')
        _plan(data.get('plan'))
        if (type(data.get('revision')) is not int or any(not isinstance(data.get(key), list)
                for key in ('operations', 'checkpoints', 'epochs')) or 'pending' not in data):
            raise AccessJournalError('Invalid journal structure')
        return data

    def _commit(self, change):
        with self._locked():
            old = self._read()
            if old != self._data:
                self._validated_session = None
                raise AccessJournalError('Journal changed since loading; reopen and revalidate')
            new = deepcopy(old)
            result = change(new)
            new['revision'] += 1
            new['updated_at_ns'] = time.time_ns()
            new = _json_copy(new)
            backup_dir = self.path.with_name(self.path.name + '.backups')
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / ('%08d.json' % old['revision'])
            if backup.exists():
                if json.loads(backup.read_text(encoding='utf-8')) != old:
                    raise AccessJournalError('Backup revision collision; original preserved')
            else:
                write_json(backup, old)
            write_json(self.path, new)
            self._data = new
            return deepcopy(result)

    def _active(self):
        if self.restored:
            raise AccessJournalError('Restored transactions cannot reopen; use a new transaction path')

    def _session(self, world_session):
        if not isinstance(world_session, str) or not world_session:
            raise AccessJournalError('Current world_session is required')
        if world_session != self._validated_session:
            raise AccessJournalError('Fresh revalidation in the current world session is required')

    def _observations(self, world_session, observations, *, restored=False):
        if not isinstance(world_session, str) or not world_session:
            raise AccessJournalError('Current world_session is required')
        observations = _json_copy(observations)
        if isinstance(observations, dict):
            if (observations.get('fresh') is not True or observations.get('exact') is not True
                    or observations.get('world_session') != world_session):
                raise AccessJournalError('Fresh exact observations from the current session are required')
            rows = observations.get('blocks')
        else:
            rows = observations
            if not isinstance(rows, list) or any(not isinstance(row, dict)
                    or row.get('fresh') is not True or row.get('exact') is not True
                    or row.get('world_session') != world_session for row in rows):
                raise AccessJournalError('Each observation needs fresh/exact current-session provenance')
        if not isinstance(rows, list):
            raise AccessJournalError('Observations must include portal blocks')
        expected = {_position(row['pos']): row['expected'] for row in self._data['plan']['blocks']}
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise AccessJournalError('Invalid block observation')
            pos = _position(row.get('pos'))
            if pos not in expected or pos in seen:
                raise AccessJournalError('Observations must cover each portal position exactly once')
            seen.add(pos)
            state = row.get('state')
            if row.get('fluid') is not False or row.get('container') is not False or not _safe_state(state):
                raise AccessJournalError('Portal contains fluid, container or unknown state')
            if state != expected[pos] and (restored or state not in _AIR):
                raise AccessJournalError('Portal state differs from its original or permitted air state')
        if seen != set(expected):
            raise AccessJournalError('Fresh observations must cover both portal positions')
        return observations

    def revalidate(self, world_session, observations):
        """Append an accepted/rejected epoch without changing operation ownership."""
        self._validated_session = None
        observations = _json_copy(observations)
        error = None
        try:
            self._observations(world_session, observations)
        except AccessJournalError as exc:
            error = str(exc)
        epoch = {'id': uuid.uuid4().hex, 'world_session': world_session,
                 'observed_at_ns': time.time_ns(), 'accepted': error is None,
                 'observations': observations}
        if error:
            epoch['reason'] = error
        self._commit(lambda data: data['epochs'].append(epoch))
        if error:
            raise AccessJournalError(error)
        self._validated_session = world_session
        return deepcopy(epoch)

    def intent(self, kind, **data):
        """Persist before dispatch. Pending intent must be reconciled, never replayed."""
        self._active()
        if not isinstance(kind, str) or not kind:
            raise AccessJournalError('Action kind is required')
        self._session(data.get('world_session', self._validated_session))
        if self.pending is not None:
            raise AccessJournalError('Unconfirmed action already pending')
        pending = {'id': uuid.uuid4().hex, 'kind': kind, 'scope': deepcopy(self.scope),
                   'world_session': self._validated_session, 'epoch_id': self._data['epochs'][-1]['id'],
                   'created_at_ns': time.time_ns(), 'data': _json_copy(data), 'request_records': []}
        def change(record):
            record['pending'] = pending
            return pending
        return self._commit(change)

    def record_request(self, request_id, **data):
        """Attach an actual dispatch ID even when dispatch raised/disconnected."""
        self._active()
        if self.pending is None:
            raise AccessJournalError('No pending action for request ID')
        if not isinstance(request_id, str) or not request_id:
            raise AccessJournalError('Request ID must be nonempty text')
        entry = {'request_id': request_id, 'recorded_at_ns': time.time_ns(), 'data': _json_copy(data)}
        def change(record):
            record['pending']['request_records'].append(entry)
            return record['pending']
        return self._commit(change)

    def _evidence(self, evidence, *, restored=False):
        evidence = _json_copy(evidence)
        self._session(evidence.get('world_session'))
        self._observations(evidence['world_session'], evidence.get('observations'), restored=restored)
        if not any(isinstance(evidence.get(key), (dict, list)) and bool(evidence[key])
                   for key in ('inventory', 'drops')):
            raise AccessJournalError('Caller inventory or drop proof is required; journal state is not proof')
        return evidence

    def confirm(self, kind, **evidence):
        """Archive pending with caller evidence, without inferring game success."""
        self._active()
        if self.pending is None or self.pending['kind'] != kind:
            raise AccessJournalError('Confirmation must match the pending action kind')
        evidence = self._evidence(evidence)
        def change(record):
            operation = record['pending']
            operation['confirmed_at_ns'] = time.time_ns()
            operation['evidence'] = evidence
            record['operations'].append(operation)
            record['pending'] = None
            return operation
        return self._commit(change)

    def checkpoint(self, stage, **data):
        """Record progress; restored is terminal and requires fresh exact evidence."""
        self._active()
        if not isinstance(stage, str) or not stage:
            raise AccessJournalError('Stage is required')
        if stage == 'restored':
            if self.pending is not None:
                raise AccessJournalError('Cannot finish with an unconfirmed action')
            data = self._evidence(data, restored=True)
        entry = {'stage': stage, 'recorded_at_ns': time.time_ns(), 'data': _json_copy(data)}
        def change(record):
            record['stage'] = stage
            record['checkpoints'].append(entry)
            return entry
        return self._commit(change)
