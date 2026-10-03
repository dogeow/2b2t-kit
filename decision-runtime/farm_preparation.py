"""Shared bounded field preparation through normal Kit APIs; planting stays separate.

Unknown selection, movement, mining or use retains a durable intent. This module
never reconciles by retrying and never changes sessions, unlocks or reconnects.
"""
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
import fcntl
import hashlib
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json
from material_jobs.acquisition import _travel
from potato_farm import _block, _counts, _gate, plan as planting_plan, valid_entity_scope
from terminal_confirmation import verified

AIR = 'Block{minecraft:air}'
WATER = 'Block{minecraft:water}[level=0]'
GRASS = 'Block{minecraft:short_grass}'
TORCH = 'Block{minecraft:torch}'
SOIL = {'minecraft:grass_block', 'minecraft:dirt'}
BOTTOM = SOIL | {'minecraft:stone', 'minecraft:deepslate'}
CROPS = {'minecraft:farmland', 'minecraft:wheat', 'minecraft:potatoes', 'minecraft:carrots',
         'minecraft:beetroots', 'minecraft:melon_stem', 'minecraft:pumpkin_stem',
         'minecraft:torchflower_crop', 'minecraft:pitcher_crop'}
BUCKET_SCOPE = 'post_single_normal_use_current_connection_target_block_and_selected_bucket_slot_server_packets_plus_vanilla_prediction_settled_and_exact_inventory_delta_after_8_ticks'
SCAN_SCOPE = 'loaded_client_cells_sampled_on_client_ticks_not_atomic_server_snapshot'
MAX_SCAN_MS, MAX_SCAN_TICKS = 30_000, 600
_HELD_LOCKS = ContextVar('held_farm_preparation_locks', default=frozenset())


class PreparationWait(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(detail); self.code = code


def plan(request):
    # Deliberately omit crop: the center's water and preparation intent are shared.
    if not isinstance(request, dict): raise ValueError('An explicit preparation request is required')
    original = planting_plan({k: request[k] for k in ('authorized', 'center', 'radius') if k in request})
    x, y, z = original['center']; radius = original['radius']
    if y < -62: raise ValueError('Preparation needs two observed layers below the center')
    source = request.get('water_source')
    if source is not None:
        planting_plan({'authorized': True, 'center': source, 'radius': 1})
        if math.hypot(source[0]-x, source[2]-z) > 32 or abs(source[1]-y) > 16:
            raise ValueError('Explicit water source must be within 32 horizontal and 16 vertical blocks')
        if source == original['center']: raise ValueError('The optional source must be distinct from the field center')
    return {'center': original['center'], 'radius': radius, 'cells': original['cells'],
            'scan_min': [x-radius-1, y-2, z-radius-1], 'scan_max': [x+radius+1, y+2, z+radius+1],
            'water_source': source[:] if source is not None else None}


def _scope(state, request):
    layout = plan(request)
    server = state.get('server'); dimension = state.get('dimension'); world = state.get('world_session')
    if not isinstance(server, str) or not server.strip() or dimension != 'minecraft:overworld' or not isinstance(world, str) or not world:
        raise PreparationWait('WAIT_CONTROL', 'A named live Overworld server/session is required')
    return {'server': server.strip().lower().removesuffix(':25565'), 'dimension': dimension,
            'center': layout['center'], 'radius': layout['radius']}


def _identity(value): return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


@contextmanager
def preparation_lock(root, state, request):
    scope = _scope(state, request); center_scope = {k: v for k, v in scope.items() if k != 'radius'}
    directory = Path(root) / 'farm-preparation' / 'locks'; directory.mkdir(parents=True, exist_ok=True)
    with (directory / (_identity(center_scope) + '.lock')).open('a') as stream:
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise PreparationWait('WAIT_CONTROL', 'This field already has an active preparation controller')
        token = _HELD_LOCKS.set(_HELD_LOCKS.get() | {str(Path(stream.name).resolve())})
        try: yield
        finally:
            _HELD_LOCKS.reset(token); fcntl.flock(stream, fcntl.LOCK_UN)


def journal_directory(root, state, request, out=None):
    scope = _scope(state, request); source = plan(request)['water_source']
    # Existing potato/wheat planting journals remain authoritative across output paths.
    for other in (Path(root) / 'farms').glob('*/registry.json'):
        saved = json.loads(other.read_text()); other_scope = saved.get('scope') or {}
        other_layout = other_scope.get('layout') or {}
        if (other_scope.get('server') == scope['server'] and other_scope.get('dimension') == scope['dimension']
                and other_layout.get('center') == scope['center']):
            for journal in Path(saved['directory']).glob('*-farm-*.json'):
                if journal.stat().st_size > 262144:
                    raise PreparationWait('WAIT_RECONCILE', 'Planting journal is too large to safely inspect')
                if json.loads(journal.read_text()).get('pending'):
                    raise PreparationWait('WAIT_RECONCILE', 'An existing crop has an unresolved action at this center; preparation cannot bypass it')
    # One registry per center also prevents changing radius from replaying its water use.
    center_scope = {k: v for k, v in scope.items() if k != 'radius'}
    registry = Path(root) / 'farm-preparation' / _identity(center_scope) / 'registry.json'
    if registry.exists():
        saved = json.loads(registry.read_text())
        if saved.get('scope') != scope or saved.get('world_session') != state['world_session'] or saved.get('water_source') != source:
            raise PreparationWait('WAIT_CONTROL', 'Saved field scope, water source or game session changed; explicit recovery is required')
        directory = Path(saved['directory']).resolve()
        if out is not None and Path(out).resolve() != directory:
            raise PreparationWait('WAIT_RECONCILE', 'Changing output cannot bypass the registered field intent')
    else:
        directory = Path(out).resolve() if out is not None else (registry.parent / 'journal').resolve()
        registry.parent.mkdir(parents=True, exist_ok=True)
        write_json(registry, {'schema': 1, 'scope': scope, 'world_session': state['world_session'],
                             'water_source': source, 'directory': str(directory)})
    directory.mkdir(parents=True, exist_ok=True)
    return directory, directory / ('farm-preparation-' + _identity(scope) + '.json')


def assert_preparation_resolved(root, state, request):
    """Read-only preflight hook for other farm entry points, before taking control."""
    scope = _scope(state, request); center_scope = {k: v for k, v in scope.items() if k != 'radius'}
    base = Path(root) / 'farm-preparation'; key = _identity(center_scope)
    lock = base / 'locks' / (key+'.lock')
    if lock.exists() and str(lock.resolve()) not in _HELD_LOCKS.get():
        with lock.open('r') as stream:
            try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise PreparationWait('WAIT_CONTROL', 'This center has an active preparation controller')
            finally: fcntl.flock(stream, fcntl.LOCK_UN)
    registry = base / key / 'registry.json'
    if not registry.exists(): return
    saved = json.loads(registry.read_text()); registered = saved.get('scope') or {}
    if ({k: v for k, v in registered.items() if k != 'radius'} != center_scope
            or saved.get('world_session') != state['world_session']):
        raise PreparationWait('WAIT_CONTROL', 'Preparation game session changed; explicit recovery is required')
    journal = Path(saved['directory']) / ('farm-preparation-'+_identity(registered)+'.json')
    if journal.exists():
        book = json.loads(journal.read_text())
        if book.get('scope') != registered or book.get('world_session') != state['world_session']:
            raise PreparationWait('WAIT_CONTROL', 'Preparation journal scope/session is inconsistent')
        if book.get('pending') or book.get('cleanup_pending'):
            raise PreparationWait('WAIT_RECONCILE', 'Preparation mutation is unresolved; another crop/output cannot bypass it')


def _complete_scan(reply, low, high):
    """Coherence means one tick; completeness is the native cursor's full volume."""
    if (not isinstance(reply, dict) or reply.get('phase') != 'done' or reply.get('scan_scope') != SCAN_SCOPE
            or type(reply.get('scan_coherent')) is not bool
            or len(low) != 3 or len(high) != 3 or any(type(v) is not int for v in list(low)+list(high))
            or any(a > b for a, b in zip(low, high))): return False
    volume = math.prod(b-a+1 for a, b in zip(low, high))
    fields = ('time', 'control_revision', 'scan_started_at', 'scan_ended_at', 'scan_start_tick',
              'scan_end_tick', 'scan_elapsed_ticks', 'scan_start_revision', 'scan_end_revision',
              'scan_cells_read', 'scan_total_cells')
    if any(type(reply.get(k)) is not int for k in fields): return False
    start, end = reply['scan_started_at'], reply['scan_ended_at']
    first, last, elapsed = reply['scan_start_tick'], reply['scan_end_tick'], reply['scan_elapsed_ticks']
    return (0 < volume <= 50_000 and reply['scan_cells_read'] == reply['scan_total_cells'] == volume
            and 0 < start <= reply['time'] <= end and 0 <= end-start <= MAX_SCAN_MS
            and 0 <= first <= last and elapsed == last-first and 0 <= elapsed <= MAX_SCAN_TICKS
            and (elapsed == 0 or end > start) and reply['scan_coherent'] == (elapsed == 0)
            and 0 <= reply['scan_start_revision'] == reply['scan_end_revision'] == reply['control_revision'])


def _rows(reply, low, high):
    if (not _complete_scan(reply, low, high)
            or type(reply.get('unloaded_chunks', 0)) is not int or reply.get('unloaded_chunks', 0) != 0
            or not isinstance(reply.get('blocks'), list) or not valid_entity_scope(reply.get('scan_entity_scope'))
            or not isinstance(reply.get('scan_entities'), list)):
        raise PreparationWait('WAIT_SCAN', 'A complete bounded native scan with stable revision, timing and loaded entity evidence is required')
    if reply['scan_entities']: raise PreparationWait('WAIT_ENTITY', 'A loaded entity intersects the preparation scan')
    result = {}
    for row in reply['blocks']:
        if not isinstance(row, dict): raise PreparationWait('WAIT_SCAN', 'Malformed scan row')
        pos = row.get('pos')
        if (not isinstance(pos, list) or len(pos) != 3 or any(type(v) is not int for v in pos)
                or not all(a <= b <= c for a, b, c in zip(low, pos, high)) or tuple(pos) in result
                or not isinstance(row.get('state'), str)
                or any(type(row.get(k)) is not bool for k in ('solid', 'fluid', 'block_entity', 'passable'))):
            raise PreparationWait('WAIT_SCAN', 'Missing typed detail, duplicate or out-of-volume row')
        if row['block_entity']: raise PreparationWait('WAIT_CONTAINER', 'Containers and block entities are protected')
        if _block(row) in CROPS: raise PreparationWait('WAIT_CROP', 'Existing crops and farmland are protected')
        result[tuple(pos)] = row
    return result


def _dry(row, allowed):
    return bool(row and _block(row) in allowed and row.get('solid') is True
                and row.get('fluid') is False and row.get('block_entity') is False)


def survey_rows(reply, layout):
    rows = _rows(reply, layout['scan_min'], layout['scan_max']); center = tuple(layout['center'])
    for p, row in rows.items():
        if row['fluid'] and (p != center or row['state'] != WATER):
            raise PreparationWait('WAIT_WATER', 'Other fluids and non-source center water are protected')
    for pos in [layout['center']] + layout['cells']:
        x, y, z = pos; soil = rows.get(tuple(pos)); above = rows.get((x, y+1, z))
        if not _dry(rows.get((x, y-1, z)), BOTTOM):
            raise PreparationWait('WAIT_FOOTING', 'An observed dry natural full-block bottom is required')
        if (x, y+2, z) in rows or above and above['state'] != GRASS:
            raise PreparationWait('WAIT_AIR', 'Headroom is occupied; only short_grass may be cleared')
        if tuple(pos) == center:
            if soil and not (_dry(soil, SOIL) or soil['state'] == WATER and soil['fluid'] is True):
                raise PreparationWait('WAIT_WATER', 'Center must be natural soil, empty bounded hole or level-0 water')
        elif not _dry(soil, SOIL):
            raise PreparationWait('WAIT_SOIL', 'Planting cells must be flat natural grass/dirt')
        if tuple(pos) != center and (type(soil.get('spawn_block_light')) is not int or not 0 <= soil['spawn_block_light'] <= 15):
            raise PreparationWait('WAIT_SCAN', 'Actual planting-cell light metadata is required before any mutation')
    x, y, z = center
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if not _dry(rows.get((x+dx, y, z+dz)), SOIL):
            raise PreparationWait('WAIT_FOOTING', 'All four water-hole walls must be observed natural soil')
    return rows


def torch_candidates(rows, layout):
    x, y, z = layout['center']; distance = layout['radius'] + 1; result = []
    for dx, dz in ((-distance, 0), (distance, 0), (0, -distance), (0, distance)):
        for support_y in (y, y-1):
            support = (x+dx, support_y, z+dz); target = (support[0], support_y+1, support[2])
            row = rows.get(support); occupied = rows.get(target)
            if not _dry(row, SOIL): continue
            if occupied and occupied['state'] not in (GRASS, TORCH): continue
            if (target[0], target[1]+1, target[2]) in rows: continue
            result.append({'support': list(support), 'target': list(target),
                           'existing': bool(occupied and occupied['state'] == TORCH)})
            break
    return result


def bucket_proved(op, reply, world, request_id, params, before, after):
    if op not in ('bucket_fill', 'bucket_place'): return False
    if not isinstance(reply, dict): return False
    proof = reply.get('bucket_water') or {}
    if not isinstance(proof, dict): return False
    if (reply.get('phase') != 'done' or reply.get('world_session') != world or reply.get('id') != request_id
            or not isinstance(request_id, str) or not request_id
            or proof.get('request_id') != request_id or proof.get('world_session') != world
            or proof.get('operation') != op or proof.get('pos') != params['pos']
            or proof.get('expected_state_before') != params['expected_state']
            or proof.get('confirmation_scope') != BUCKET_SCOPE
            or proof.get('use_count') != 1 or type(proof.get('use_count')) is not int
            or any(proof.get(k) is not True for k in ('confirmed', 'server_block_update_seen',
                'server_block_confirmed', 'server_inventory_update_seen', 'server_inventory_confirmed'))
            or proof.get('unknown_outcome') is not False or proof.get('automatic_retry_allowed') is not False):
        return False
    a, b = _counts(before), _counts(after); expected = a.copy()
    consume, produce = ('minecraft:bucket', 'minecraft:water_bucket') if op == 'bucket_fill' else ('minecraft:water_bucket', 'minecraft:bucket')
    if (before.get('hand', {}).get('item') != consume or before['hand'].get('count') != 1
            or after.get('hand', {}).get('item') != produce or after['hand'].get('count') != 1
            or before.get('selected_slot') != after.get('selected_slot')): return False
    expected[consume] -= 1; expected[produce] += 1
    if not expected[consume]: del expected[consume]
    if b != expected: return False
    for name, item in (('empty_buckets', 'minecraft:bucket'), ('water_buckets', 'minecraft:water_bucket')):
        for suffix, counts in (('before', a), ('after', b)):
            if type(proof.get(name+'_'+suffix)) is not int or proof[name+'_'+suffix] != counts[item]: return False
    state = proof.get('server_observed_state')
    return state == WATER if op == 'bucket_place' else state in (AIR, WATER) or isinstance(state, str) and state.startswith('Block{minecraft:water}[level=')


class _PreparationTravelClient:
    """Borrow existing route planning while journaling each dispatched navigation."""
    def __init__(self, runner): self.runner = runner
    def __getattr__(self, name): return getattr(self.runner.c, name)
    def status(self): return self.runner.status()
    def request(self, op, **params):
        if op == 'scan': return self.runner.scan(params['min'], params['max'])[0]
        if op != 'navigate':
            raise PreparationWait('WAIT_ROUTE', 'Preparation travel may only scan or navigate')
        point = params['target']
        def arrived(reply, before, after):
            nav = reply.get('material_air_navigation') or {}
            return (nav.get('phase') == 'confirmed' and nav.get('outcome') == 'done'
                    and nav.get('stable_ticks', 0) >= 8 and nav.get('restored_ticks', 0) >= 8
                    and math.dist(after['pos'], point) <= .4)
        return self.runner.action('navigate', params, arrived)


class _Runner:
    def __init__(self, c, layout, path, book, checkpoint, no_move, max_torches):
        self.c, self.layout, self.path, self.book = c, layout, path, book
        self.checkpoint, self.no_move, self.max_torches = checkpoint, no_move, max_torches
        self.hurt = book.setdefault('recent_hurt_at', c.status().get('recent_hurt_at'))
        if type(self.hurt) is not int: raise PreparationWait('WAIT_SAFETY', 'Injury marker is unavailable')
        self.save()

    def save(self): write_json(self.path, self.book)

    def status(self):
        self.checkpoint(); state = self.c.status(); _gate(self.c, state, self.hurt)
        if state.get('food', 0) < 18: raise PreparationWait('WAIT_SAFETY', 'Food or injury changed; leave recovery to the guard')
        _counts(state)
        return state

    def scan(self, low, high):
        before = self.status(); reply = self.c.request('scan', min=list(low), max=list(high), details=True)
        _gate(self.c, reply, self.hurt)
        if reply.get('time', 0) <= before['time']: raise PreparationWait('WAIT_SCAN', 'Scan is not a later native observation')
        rows = _rows(reply, low, high)
        return reply, rows

    def survey(self):
        reply, _ = self.scan(self.layout['scan_min'], self.layout['scan_max'])
        return reply, survey_rows(reply, self.layout)

    def action(self, op, params, proof):
        if self.book.get('pending') or self.book.get('cleanup_pending'):
            raise PreparationWait('WAIT_RECONCILE', 'An original mutation remains unresolved; no repeated action sent')
        before = self.status()
        self.book['pending'] = {'op': op, 'params': params, 'before': before, 'stage': 'intent_before_dispatch',
                                'request_id_before': getattr(self.c, 'last', None)}
        self.save()
        try: reply = self.c.checked(op, **params)
        except (RuntimeError, OSError, ValueError, KeyError) as error:
            self.book['pending'].update(stage='dispatch_outcome_unknown',
                                        request_id_after=getattr(self.c, 'last', None), detail=str(error))
            self.save(); raise PreparationWait('WAIT_RECONCILE', str(error)) from error
        self.book['pending'].update(stage='returned_pending_proof', receipt=reply); self.save()
        after = self.status()
        if (reply.get('id') != getattr(self.c, 'last', None) or reply.get('world_session') != self.c.world
                or not proof(reply, before, after)):
            raise PreparationWait('WAIT_RECONCILE', 'Native result or exact outcome proof is incomplete; intent retained, no repeat')
        self.book['actions'].append(self.book['pending']); self.book['pending'] = None; self.save()
        return reply

    def select(self, item, one=False):
        state = self.status(); hand = state.get('hand') or {}
        if hand.get('item') == item and hand.get('count', 0) > 0 and (not one or hand['count'] == 1): return
        carried = [r for r in state['inventory'] if r['slot'] < 36 and r['item'] == item and r['count'] > 0 and (not one or r['count'] == 1)]
        if not carried: raise PreparationWait('WAIT_INVENTORY', 'A carried '+item+(' in an exact single bucket slot' if one else '')+' is required')
        self.action('select_item', {'item': item, 'slot': carried[0]['slot']},
                    lambda reply, before, after: after.get('hand', {}).get('item') == item
                    and after['hand'].get('count', 0) > 0 and (not one or after['hand']['count'] == 1)
                    and _counts(before) == _counts(after))

    def go(self, pos):
        target = [pos[0]+.5, pos[1]+1.6, pos[2]+.5]; state = self.status()
        if self.no_move:
            eye = [state['pos'][0], state['pos'][1]+1.62, state['pos'][2]]
            if math.dist(eye, [pos[0]+.5, pos[1]+.5, pos[2]+.5]) > 4.5:
                raise PreparationWait('WAIT_REACH', 'No-move mode requires the exact interaction target already in reach')
            return
        here = state['pos']
        if math.hypot(target[0]-here[0], target[2]-here[2]) > 32:
            raise PreparationWait('WAIT_ROUTE', 'Preparation only handles nearby air routes within 32 horizontal blocks')
        if state.get('air_only_navigation_protocol', 0) < 2:
            raise PreparationWait('WAIT_ROUTE', 'Native stable air-only navigation protocol 2 is required')
        trace = []
        _travel(_PreparationTravelClient(self), target, self.checkpoint, trace,
                clearance_padding=2.32, obstacle_margin=5.1)
        self.book['last_travel'] = trace; self.save()

    def mine(self, pos, expected):
        self.go(pos); _, rows = self.survey()
        if rows.get(tuple(pos), {}).get('state') != expected:
            raise PreparationWait('WAIT_SCAN', 'Authorized grass/center soil changed before mining')
        if expected != GRASS:
            counts = _counts(self.status())
            tool = next(('minecraft:'+name+'_shovel' for name in ('netherite', 'diamond', 'iron', 'stone', 'wooden', 'golden')
                         if counts['minecraft:'+name+'_shovel']), None)
            if tool is None: raise PreparationWait('WAIT_TOOL', 'Center excavation needs an actual carried shovel')
            self.select(tool)
        params = {'pos': pos, 'expected_state': expected, 'seconds': 10}
        def proved(reply, before, after):
            if not verified('mine_block', reply, self.c.world, self.c.last, params): return False
            _, observed = self.survey(); return tuple(pos) not in observed
        self.action('mine_block', params, proved)

    def ensure_water(self, rows):
        center = self.layout['center']
        if rows.get(tuple(center), {}).get('state') == WATER: return
        if self.status().get('bucket_water_protocol', 0) < 1:
            raise PreparationWait('WAIT_CONTROL', 'Native single-use confirmed bucket protocol 1 is required before excavation')
        if not _counts(self.status())['minecraft:water_bucket']:
            source = self.layout['water_source']
            if source is None: raise PreparationWait('WAIT_WATER_SOURCE', 'Carry water or declare an exact existing water source; no water search is performed')
            self.go(source); low = [source[0]-1, source[1], source[2]-1]; high = [source[0]+1, source[1]+2, source[2]+1]
            _, source_rows = self.scan(low, high)
            if source_rows.get(tuple(source), {}).get('state') != WATER or any(r['fluid'] and _block(r) != 'minecraft:water' for r in source_rows.values()):
                raise PreparationWait('WAIT_WATER_SOURCE', 'Declared source is not observed level-0 water with a protected clear vicinity')
            self.select('minecraft:bucket', one=True)
            params = {'pos': source, 'expected_state': WATER, 'expected_hand': 'minecraft:bucket'}
            self.action('bucket_fill', params, lambda reply, before, after: bucket_proved('bucket_fill', reply, self.c.world, self.c.last, params, before, after))
        _, rows = self.survey()
        # Clear only the explicitly bounded planting/center head cells.
        self.clear_grass(rows)
        _, rows = self.survey(); soil = rows.get(tuple(center))
        if soil and _dry(soil, SOIL): self.mine(center, soil['state'])
        self.go(center); _, rows = self.survey()
        if rows.get(tuple(center), {}).get('state') == WATER: return
        if tuple(center) in rows: raise PreparationWait('WAIT_WATER', 'Center hole did not remain empty; no bucket use sent')
        self.select('minecraft:water_bucket', one=True)
        support = [center[0], center[1]-1, center[2]]
        params = {'pos': center, 'expected_state': AIR, 'expected_hand': 'minecraft:water_bucket',
                  'support': support, 'face': 'up', 'expected_support_state': rows[tuple(support)]['state']}
        self.action('bucket_place', params, lambda reply, before, after: bucket_proved('bucket_place', reply, self.c.world, self.c.last, params, before, after))

    def clear_grass(self, rows):
        for pos in [self.layout['center']] + self.layout['cells']:
            head = [pos[0], pos[1]+1, pos[2]]
            if rows.get(tuple(head), {}).get('state') == GRASS: self.mine(head, GRASS)

    def lit(self, rows):
        return all(type(rows[tuple(pos)].get('spawn_block_light')) is int and 9 <= rows[tuple(pos)]['spawn_block_light'] <= 15 for pos in self.layout['cells'])

    def validate_history(self, rows):
        center = tuple(self.layout['center']); state = rows.get(center, {}).get('state', AIR)
        for action in self.book['actions']:
            op = action.get('op'); params = action.get('params') or {}
            if op == 'bucket_place' and state != WATER:
                raise PreparationWait('WAIT_RECONCILE', 'Previously confirmed center water changed; no automatic second placement')
            if op == 'bucket_fill' and state != WATER and not _counts(self.status())['minecraft:water_bucket']:
                raise PreparationWait('WAIT_RECONCILE', 'Previously filled water is missing; the shared source step will not repeat')
            if op == 'mine_block':
                pos = tuple(params['pos']); observed = rows.get(pos)
                allowed = WATER if pos == center else TORCH
                if observed and observed['state'] != allowed:
                    raise PreparationWait('WAIT_RECONCILE', 'Previously cleared soil/grass changed; no second excavation')
            if op == 'interact':
                p = params['pos']; target = (p[0], p[1]+1, p[2])
                if rows.get(target, {}).get('state') != TORCH:
                    raise PreparationWait('WAIT_RECONCILE', 'Previously observed torch is missing; no automatic replacement')

    def torch(self, candidate):
        support, target = candidate['support'], candidate['target']; self.go(support)
        _, rows = self.survey()
        current = next((r for r in torch_candidates(rows, self.layout) if r['support'] == support), None)
        if current is None or current['existing']: raise PreparationWait('WAIT_SCAN', 'Torch station changed; no placement sent')
        if rows.get(tuple(target), {}).get('state') == GRASS: self.mine(target, GRASS)
        self.select('minecraft:torch'); _, rows = self.survey()
        if tuple(target) in rows or not _dry(rows.get(tuple(support)), SOIL):
            raise PreparationWait('WAIT_SCAN', 'Torch support or exact target changed after item selection')
        params = {'pos': support, 'face': 'up', 'expected_state': rows[tuple(support)]['state'], 'expected_hand': 'minecraft:torch'}
        def proved(reply, before, after):
            expected = _counts(before); expected['minecraft:torch'] -= 1
            if not expected['minecraft:torch']: del expected['minecraft:torch']
            last = reply.get('time', 0); frames = []
            for _ in range(2):
                scan, observed = self.survey()
                if (scan['time'] <= last or observed.get(tuple(target), {}).get('state') != TORCH
                        or _counts(scan) != expected): return False
                frames.append(scan['time']); last = scan['time']
            self.book['pending']['observed_times'] = frames
            return True
        self.action('interact', params, proved)


def run(c, request, out=None, checkpoint=lambda: None, *, no_move=False, max_torches=4, _locked=False):
    layout = plan(request)
    if type(max_torches) is not int or not 1 <= max_torches <= 4: raise ValueError('Preparation torch budget is limited to 1..4')
    # Registry lookup and pending checks precede every mutation, including movement.
    state = c.status(); state = {**state, 'server': c.server}
    with nullcontext() if _locked else preparation_lock(c.root, state, request):
        directory, path = journal_directory(c.root, state, request, out)
        scope = _scope(state, request)
        book = json.loads(path.read_text()) if path.exists() else {'schema': 1, 'scope': scope,
            'world_session': c.world, 'water_source': layout['water_source'], 'actions': [], 'pending': None}
        def result(code=None, detail=''):
            return {'phase': 'done' if code is None else 'waiting', 'code': code, 'detail': detail,
                    'center': layout['center'], 'radius': layout['radius'], 'planting_cells': len(layout['cells']),
                    'torches_placed': sum(a.get('op') == 'interact' for a in book.get('actions', [])),
                    'journal': str(path), 'server_verified': False, 'automatic_retry_allowed': False,
                    'verification_scope': 'native_mining_and_bucket_receipts_plus_distinct_loaded_client_torch_and_final_crop_light_scans'}
        if book.get('scope') != scope or book.get('world_session') != c.world or book.get('water_source') != layout['water_source']:
            return result('WAIT_CONTROL', 'Saved scope/session changed; explicit recovery is required')
        if book.get('schema') != 1 or not isinstance(book.get('actions'), list) or any(not isinstance(a, dict) for a in book['actions']):
            return result('WAIT_CONTROL', 'Preparation journal is malformed; explicit recovery is required')
        if book.get('pending') or book.get('cleanup_pending'):
            return result('WAIT_RECONCILE', 'An original preparation or cleanup mutation is unresolved; no repeated action sent')
        try:
            runner = _Runner(c, layout, path, book, checkpoint, no_move, max_torches)
            _, rows = runner.survey()
            runner.validate_history(rows)
            runner.ensure_water(rows); _, rows = runner.survey(); runner.clear_grass(rows)
            for _ in range(max_torches):
                _, rows = runner.survey()
                if runner.lit(rows): break
                choices = [p for p in torch_candidates(rows, layout) if not p['existing']]
                if not choices: break
                runner.torch(choices[0])
            times = []
            for _ in range(2):
                scan, rows = runner.survey()
                if rows.get(tuple(layout['center']), {}).get('state') != WATER or any((p[0], p[1]+1, p[2]) in rows for p in [layout['center']] + layout['cells']):
                    raise PreparationWait('WAIT_SCAN', 'Final water or planting headroom is unprepared')
                if not runner.lit(rows): raise PreparationWait('WAIT_LIGHT', 'Measured planting-cell spawn_block_light remains below 9; no geometry-based completion')
                if times and scan['time'] <= times[-1]: raise PreparationWait('WAIT_SCAN', 'Final observations are not distinct')
                times.append(scan['time'])
            book.update(complete=True, final_observed_times=times,
                        final_crop_light={','.join(map(str, p)): rows[tuple(p)]['spawn_block_light'] for p in layout['cells']})
            runner.save(); return result()
        except (PreparationWait, RuntimeError, OSError, ValueError, KeyError) as error:
            code = 'WAIT_RECONCILE' if book.get('pending') else getattr(error, 'code', 'WAIT_CONTROL')
            return result(code, str(error))
