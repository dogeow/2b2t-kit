"""Persistent authorized exterior lighting regions, using Kit APIs without AI/UI.

A queued batch is never goal completion. Interrupted original batches stay pending;
changing output/profile cannot bypass the server/dimension registry or torch intents.
"""
from contextlib import contextmanager
from copy import deepcopy
import argparse
import fcntl
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from lighting_cli import (LightingRun, bounds, candidates, protection_boxes, risk_counts,
                          scan_cells, stock, validate_budget, validate_movement_bounds, write_json)
from material_jobs.protocol import server_key
from safety_interlock import require_unlocked


class RegionsPaused(RuntimeError):
    pass


def validate_profile(value):
    profile = deepcopy(value)
    if (not isinstance(profile, dict) or profile.get('schema') != 1
            or profile.get('authorized') is not True
            or not isinstance(profile.get('server'), str) or not profile['server'].strip()
            or profile.get('dimension') != 'minecraft:overworld'):
        raise ValueError('An explicitly authorized server/Overworld lighting profile is required')
    profile['server'] = server_key(profile['server'].strip())
    profile['protected'] = protection_boxes(profile.get('protected', []))
    if profile.get('movement_bounds') is None:
        raise ValueError('Region travel needs an explicit authorized movement_bounds box')
    profile.setdefault('batch_torches', 8)
    validate_budget(profile['batch_torches'])
    profile.setdefault('max_batches_per_region', 8)
    if type(profile['max_batches_per_region']) is not int or not 1 <= profile['max_batches_per_region'] <= 64:
        raise ValueError('Max batches per region must be 1..64')
    regions = profile.get('regions')
    if not isinstance(regions, list) or not 1 <= len(regions) <= 256:
        raise ValueError('Register 1..256 explicit lighting regions')
    names = set()
    for region in regions:
        if (not isinstance(region, dict) or not isinstance(region.get('name'), str)
                or not region['name'].strip() or len(region['name']) > 80 or region['name'] in names):
            raise ValueError('Every lighting region needs a unique nonempty name')
        names.add(region['name'])
        low, high = bounds(region.get('min'), region.get('max'))
        if (high[1] - low[1] < 24 or any(abs(p[i]) > 30_000_000 for p in (low, high) for i in (0, 2))):
            raise ValueError('Lighting regions need bounded coordinates and enough guarded height')
        validate_movement_bounds(profile.get('movement_bounds'), low, high)
        region['min'], region['max'] = list(low), list(high)
    return profile


def _read(path):
    return json.loads(Path(path).read_text())


class RegionsWorker:
    def __init__(self, root, profile, out=None, *, observer=None, batch=None):
        self.root, self.profile = Path(root), validate_profile(profile)
        key = hashlib.sha256((self.profile['server'] + '|' + self.profile['dimension']).encode()).hexdigest()[:20]
        self.home = self.root / 'lighting-regions' / key
        self.home.mkdir(parents=True, exist_ok=True)
        with (self.home / 'registry.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            registry = self.home / 'registry.json'
            directory = Path(out).resolve() if out is not None else (self.home / 'journal').resolve()
            if registry.exists():
                registered = _read(registry)
                if registered.get('profile') != self.profile:
                    raise ValueError('This server/dimension already has a different lighting profile')
                if out is not None and directory != Path(registered['directory']):
                    raise ValueError('Changing output cannot bypass the original lighting journal')
                directory = Path(registered['directory'])
            else:
                write_json(registry, {'profile': self.profile, 'directory': str(directory)})
            self.out = directory
            self.out.mkdir(parents=True, exist_ok=True)
            self.path, self.control = self.out / 'regions.json', self.out / 'control.json'
            existing = self.path.exists()
            self.book = _read(self.path) if existing else {
                'schema': 1, 'profile': self.profile, 'phase': 'not_started', 'world_session': None,
                'cursor': 0, 'campaign': 0, 'dispatch_sequence': 0, 'pending': None, 'batches': [], 'audits': [], 'last_control': None,
                'parking_lease': None, 'last_revision': None, 'coverage_complete': False, 'ai_calls': 0}
            if (self.book.get('schema') != 1 or self.book.get('profile') != self.profile
                    or self.book.get('ai_calls') != 0 or type(self.book.get('cursor')) is not int
                    or not 0 <= self.book['cursor'] <= len(self.profile['regions'])
                    or not isinstance(self.book.get('batches'), list)):
                raise ValueError('Original lighting journal is malformed; no control acquired')
            if not existing:
                self.save()
        self.observer = observer or self.observe
        self.batch = batch or NativeBatch(self)
        self.opening = self.cleaning = False

    def observe(self):
        from live_snapshot import read_fresh
        return read_fresh(self.root)

    def save(self):
        write_json(self.path, self.book)

    @contextmanager
    def worker_lock(self):
        with (self.home / 'worker.lock').open('a+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RegionsPaused('Another lighting region worker is active') from error
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def status(self):
        value = deepcopy(self.book)
        try:
            with self.worker_lock():
                value['worker_running'] = False
        except RegionsPaused:
            value['worker_running'] = True
        value['journal'] = str(self.out)
        return value

    def command(self, action):
        if action not in ('pause', 'stop'):
            raise ValueError('Only pause/stop are asynchronous controls')
        command = {'id': uuid.uuid4().hex, 'action': action}
        write_json(self.control, command)
        return command

    def gate(self, state, client=None):
        require_unlocked(self.root, state)
        if (state.get('connected') is not True or server_key(state.get('server')) != self.profile['server']
                or state.get('dimension') != self.profile['dimension']
                or not state.get('world_session')
                or self.book['world_session'] not in (None, state['world_session'])):
            raise RegionsPaused('World changed or disconnected; no reconnect')
        if (state.get('manual_movement') is not False or state.get('health') != 20
                or state.get('food', 0) < 18 or state.get('under_water') is not False
                or not state.get('guard_armed') or not state.get('guard_pve_only') or not state.get('flight')):
            raise RegionsPaused('Manual input or survival protection is not ready')
        if self.control.exists():
            command = _read(self.control)
            if command.get('id') != self.book['last_control']:
                self.book['last_control'] = command.get('id')
                self.save()
                raise RegionsPaused('Requested ' + str(command.get('action')))
        if client is not None:
            from material_jobs_backend import owns_material_state
            if not owns_material_state(client, state):
                raise RegionsPaused('Foreign revision or material lease; preserve original pending batch')
            inflight = getattr(client, 'native_inflight', None)
            if isinstance(inflight, dict) and self.book.get('pending') is not None:
                keys = ('request_id', 'op', 'world_session', 'task_session', 'lease_id',
                        'base_revision', 'expected_revision')
                proof = {key: inflight.get(key) for key in keys}
                if self.book['pending'].get('native_request') != proof:
                    self.book['pending']['native_request'] = proof
                    self.save()
        elif not self.opening:
            position, movement = state.get('pos'), self.profile['movement_bounds']
            if (not isinstance(position, list) or len(position) != 3
                    or any(type(value) not in (int, float) or not math.isfinite(value) for value in position)
                    or any(not movement['min'][i] <= position[i] <= movement['max'][i] + 1 for i in range(3))):
                raise RegionsPaused('Current position is outside the authorized movement box')
            lease = state.get('supervision_lease') or {}
            if (self.book.get('last_revision') is not None
                    and state.get('control_revision') != self.book['last_revision']
                    or lease.get('kind') == 'parking' and self.book.get('parking_lease') is not None
                    and lease.get('id') != self.book['parking_lease']
                    or lease.get('kind') not in (None, 'parking')
                    or state.get('material_task', {}).get('occupied')
                    or any(state.get(k) for k in ('borer_active', 'chopping', 'navigating', 'printing',
                                                 'planter_active', 'feeder_active', 'fisher_active', 'native_material_busy'))
                    or state.get('build_job', {}).get('active')
                    or state.get('professional_printer', {}).get('enabled') or state.get('screen')):
                raise RegionsPaused('Another native controller or interface is active')

    def reconcile_travel(self):
        """Archive only cancelled travel with proof no construction was admitted."""
        with self.worker_lock():
            pending = self.book.get('pending')
            if pending is None:
                return {**deepcopy(self.book), 'worker_running': False, 'journal': str(self.out)}
            if (pending.get('stage') != 'travel'
                    or pending.get('handoff') != 'world_manual_or_lease_changed'
                    or 'air-only path changed; no blocks were excavated' not in pending.get('error', '')):
                raise RegionsPaused('Pending action is not a known interrupted travel; no reconciliation')
            state = self.observer()
            require_unlocked(self.root, state)
            if (not state.get('connected') or state.get('world_session') != pending.get('world_session')
                    or server_key(state.get('server')) != self.profile['server']
                    or state.get('dimension') != self.profile['dimension']
                    or state.get('manual_movement') is not False or state.get('screen')
                    or state.get('health', 0) < 18 or state.get('navigating')
                    or state.get('native_material_busy') or state.get('material_task', {}).get('occupied')
                    or state.get('supervision_lease') or state.get('phase') != 'stopped'
                    or state.get('detail') != '手动移动接管'):
                raise RegionsPaused('Original travel has no current authoritative manual-stop handoff')
            events_path = Path(pending['directory']) / 'events.jsonl'
            if not events_path.is_file() or events_path.stat().st_size > 8_000_000:
                raise RegionsPaused('Original bounded travel journal unavailable')
            data = events_path.read_bytes()
            events = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
            allowed = {'material_session', 'snapshot', 'scan', 'navigate'}
            if (not events or any(event.get('op') not in allowed
                    or event.get('world_session') != pending['world_session']
                    or event.get('params', {}).get('task_session') not in
                        ((None, pending['task_session']) if event.get('op') in ('snapshot', 'scan')
                         else (pending['task_session'],))
                    or event.get('inventory_delta', {}).get('minecraft:torch', 0) != 0 for event in events)):
                raise RegionsPaused('Original journal includes an unknown or construction operation')
            rejected = [event for event in events if event.get('op') == 'navigate'
                        and event.get('phase') == 'waiting'
                        and event.get('detail') == 'air-only path changed; no blocks were excavated']
            if (not rejected or state.get('control_revision', -1) <= max(event.get('revision_after', -1) for event in events)):
                raise RegionsPaused('Native route stop or later manual revision unavailable')
            # No attempt is marked complete. A future resume creates a new route
            # from the actual pose; original requests and this pending remain archived.
            record = {'outcome': 'manual_cancelled_travel_without_construction',
                      'construction_completed': False, 'request_replayed': False,
                      'original_pending': deepcopy(pending),
                      'events_sha256': hashlib.sha256(data).hexdigest(),
                      'native_waiting_request': rejected[-1]['request_id'],
                      'observed': {key: state.get(key) for key in ('time', 'world_session',
                                   'control_revision', 'phase', 'detail', 'health', 'pos')}}
            self.book.setdefault('pending_reconciliations', []).append(record)
            self.book.update(pending=None, phase='waiting_resume', last_revision=None, parking_lease=None)
            self.save()
        return self.status()

    def run(self, *, resume=False, audit_only=False):
        with self.worker_lock():
            if self.book['pending']:
                raise RegionsPaused('Original pending batch needs read-only reconciliation; no replay')
            state = self.observer()
            # Explicit resume may start a fresh world only when no original
            # uncertain action remains and the player-cleared safety lock passes.
            if resume or not audit_only:
                require_unlocked(self.root, state)
                self.book.update(last_revision=None, parking_lease=None)
                if resume and self.book['world_session'] != state.get('world_session'):
                    self.book['world_session'] = None
            if not resume and not audit_only:
                self.book.update(campaign=self.book.get('campaign', 0) + 1, cursor=0)
            self.gate(state)
            self.book.update(world_session=state['world_session'], phase='running', coverage_complete=False, reason=None)
            self.save()
            try:
                if not audit_only:
                    while self.book['cursor'] < len(self.profile['regions']):
                        index = self.book['cursor']
                        region = self.profile['regions'][index]
                        prior = [b for b in self.book['batches'] if b['region_index'] == index
                                 and b.get('campaign') == self.book.get('campaign')]
                        if len(prior) >= self.profile['max_batches_per_region']:
                            self.book['cursor'] += 1
                            self.save()
                            continue
                        current = self.observer()
                        self.gate(current)
                        if stock(current) < 1:
                            self.book.update(phase='waiting_materials', reason='No torches; supply then resume')
                            self.save()
                            return {**deepcopy(self.book), 'worker_running': False, 'journal': str(self.out)}
                        result = self.dispatch(index, region, audit=False)
                        if not result['placed_verified'] or result['eligible_remaining'] == 0:
                            self.book['cursor'] += 1
                            self.save()
                self.book['audits'] = []
                for index, region in enumerate(self.profile['regions']):
                    self.gate(self.observer())
                    self.dispatch(index, region, audit=True)
                dark_remaining = any(a['unprotected_dark_floor'] > 0 for a in self.book['audits'])
                self.book.update(phase='audited_with_remaining_risk' if dark_remaining else 'audited', coverage_complete=True,
                                 ordinary_zombie_light_clear=all(a['unprotected_dark_floor'] == 0 for a in self.book['audits']),
                                 goal_complete=False,
                                 audit_scope='current_loaded_profile_boxes_sampled_sequentially_not_whole_island_not_all_mob_rules')
            except BaseException as error:
                self.book.update(phase='waiting', reason=type(error).__name__ + ': ' + str(error))
                self.save()
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
            self.save()
        return self.status()

    def dispatch(self, index, region, *, audit):
        number = self.book.get('dispatch_sequence', 0) + 1
        directory = self.out / ('audit-' if audit else 'batch-') / f'{number:05d}'
        if directory.exists():
            raise RegionsPaused('Original batch directory exists; will not overwrite or replay')
        directory.mkdir(parents=True)
        self.book['dispatch_sequence'] = number
        self.book['pending'] = {'region_index': index, 'mode': 'audit' if audit else 'lighting',
                                'directory': str(directory), 'stage': 'before_native_control'}
        self.save()
        result = self.batch(region, directory, audit=audit)
        if result.get('park_native_confirmed') is not True:
            raise RegionsPaused('Native parking unproven; original batch remains pending')
        result = {**result, 'region_index': index, 'campaign': self.book.get('campaign'), 'directory': str(directory)}
        self.book['parking_lease'] = result.get('parking_lease')
        self.book['last_revision'] = result.get('control_revision')
        self.book['audits' if audit else 'batches'].append(result)
        self.book['pending'] = None
        self.save()
        return result


class NativeBatch:
    def __init__(self, owner):
        self.owner = owner

    def __call__(self, region, directory, *, audit):
        from material_client import MaterialClient
        from material_jobs.acquisition import _travel
        owner = self.owner

        class RegionClient(MaterialClient):
            def request(self, op, **params):
                if op == 'navigate' and not owner.cleaning:
                    movement = owner.profile['movement_bounds']
                    start, target = self.status()['pos'], params['target']
                    low = [math.floor(min(start[i], target[i]) - (.35 if i != 1 else 0)) for i in range(3)]
                    high = [math.floor(max(start[i], target[i]) + (.35 if i != 1 else 1.8)) for i in range(3)]
                    if any(low[i] < movement['min'][i] or high[i] > movement['max'][i] for i in range(3)):
                        raise RegionsPaused('Region travel would leave the authorized movement box')
                return super().request(op, **params)

            def raw(self, *args, **kwargs):
                state = super().raw(*args, **kwargs)
                if not owner.cleaning:
                    owner.gate(state, None if owner.opening else self)
                return state

        state = owner.observer()
        owner.gate(state)
        if not audit and stock(state) < 1:
            raise RegionsPaused('No torches; supply materials before resuming')
        low, high = region['min'], region['max']
        park = [(low[0] + high[0]) / 2 + .5, high[1] - 2, (low[2] + high[2]) / 2 + .5]
        client = runner = None
        park_started = False
        try:
            owner.opening = True
            from material_client import Client
            survey=Client(owner.root,directory/'opening-survey',server=owner.profile['server'])
            px,pz=math.floor(park[0]),math.floor(park[2])
            column=survey.request('scan',min=[px,-64,pz],max=[px,319,pz],details=True)
            scan_cells(column,[px,-64,pz],[px,319,pz],survey.world)
            solid_top=max((row['pos'][1]+1 for row in column['blocks'] if row.get('fluid')or not row.get('passable',False)),default=None)
            if solid_top is None or solid_top+24>315:raise RegionsPaused('No bounded current column for safe parking')
            park[1]=solid_top+24
            arrival=[park[0],solid_top+1.5,park[2]]
            write_json(directory/'arrival-height-plan.json',{'actual_column':column,'arrival':arrival,'safe_park':park})
            client = RegionClient(owner.root, directory, server=owner.profile['server'], remote_finish='guard',
                                  park_target=park, record_experience=False)
            owner.opening = False
            owner.book['pending'].update(stage='travel', world_session=client.world,
                                         task_session=client.task, lease=client.heartbeat.id)
            owner.save()
            trace = []
            _travel(client, arrival, lambda: owner.gate(client.status(), client), trace,
                    clearance_padding=2.32, obstacle_margin=5.1)
            write_json(directory / 'arrival-route.json', trace)
            runner = LightingRun(client, low, high,
                                 1 if audit else min(owner.profile['batch_torches'], stock(client.status())),
                                 directory, client.status(), protected=owner.profile['protected'],
                                 movement_bounds=owner.profile.get('movement_bounds'))
            owner.book['pending']['stage'] = 'audit' if audit else 'lighting'
            owner.save()
            if audit:
                client.start_progress('补光复核', 1, phase=region['name'])
                reply = runner.scan(low, high, 'current-region-audit.json')
                cells = scan_cells(reply, low, high, client.world)
                result = {**risk_counts(cells, owner.profile['protected']),
                          'observed_at': reply.get('scan_ended_at', reply.get('time')),
                          'eligible_remaining': len(candidates(cells, low, high, protected=owner.profile['protected']))}
            else:
                runner.work()
                result = {'placed_verified': len(runner.report['placed']),
                          'eligible_remaining': runner.report['progress']['eligible_candidates'],
                          'unprotected_dark_floor': runner.report['remaining_unprotected_risk']}
            owner.cleaning = True
            park_started = True
            runner.park()
            result.update(park_native_confirmed=runner.report['park_native_confirmed'],
                          parking_lease=client.heartbeat.id,
                          control_revision=_read(directory / 'final-snapshot.json')['control_revision'])
            return result
        except BaseException as error:
            owner.book['pending']['error'] = type(error).__name__ + ': ' + str(error)
            owner.book['pending']['uncertain_request'] = deepcopy(owner.book['pending'].get('native_request'))
            owner.save()
            # The same pending batch remains locked. Never repeat a failed park,
            # call a generic finish fallback, or retry uncertain work here.
            if client is not None:
                owner.cleaning = True
                if runner is not None and not park_started:
                    try:
                        runner.park()
                    except BaseException as cleanup:
                        owner.book['pending']['cleanup_error'] = type(cleanup).__name__ + ': ' + str(cleanup)
                        owner.save()
                self.wait_unresolved(client)
            raise
        finally:
            owner.opening = owner.cleaning = False

    def wait_unresolved(self, client):
        """Keep the lease/flock alive after uncertain work; no retry or movement."""
        from material_shutdown import drain_pending
        from safety_interlock import record_material_health_exit
        owner, last_saved = self.owner, 0
        owner.book['phase'] = 'waiting_unresolved'
        owner.save()
        while True:
            try:
                state = client.raw()  # Same heartbeat; never publishes a new request.
            except (OSError, RuntimeError, ValueError) as error:
                owner.book['pending']['observation_error'] = type(error).__name__ + ': ' + str(error)
                owner.save()
                time.sleep(.25)
                continue
            lease = state.get('supervision_lease') or {}
            stop = state.get('control_stop') or {}
            if (state.get('world_session') != client.world or not state.get('connected')
                    or state.get('manual_movement') or lease.get('id') != client.heartbeat.id
                    or lease.get('job_session') != client.task
                    or stop.get('kind') in ('manual', 'emergency') and stop.get('revision') == state.get('control_revision')):
                client._record_health_stop('Lighting pending yielded after owned health loss')
                client.heartbeat.close()
                owner.book['pending']['handoff'] = 'world_manual_or_lease_changed'
                owner.save()
                return
            if type(state.get('health')) in (int, float) and state['health'] < 14:
                record_material_health_exit(owner.root, state, 'Critical health while lighting remained pending')
                client.heartbeat.close()
                owner.book['pending']['handoff'] = 'critical_health_native_supervision'
                owner.save()
                return
            safety = state.get('supervision_safety') or {}
            if (client._owned_guarded_finish_state(state, 'parking') and client.park_near(state)
                    and safety.get('lease') == client.heartbeat.id and safety.get('job_session') == client.task
                    and safety.get('action') == 'KEEP_PVE_GUARD'):
                owner.book['pending']['handoff'] = 'late_owned_native_parking_observed_read_only'
                owner.save()
                return
            # Calm protection is not completion of the original navigation.
            # drain_pending alone validates the same original request and adopts
            # only its terminal owned revision. No cleanup when still running.
            if (state.get('phase') in ('done', 'waiting', 'stopped', 'error')
                    and not state.get('navigating') and not state.get('native_material_busy')
                    and not state.get('guard_busy') and client.park_near(state)
                    and (state.get('menu') or {}).get('type') == 'InventoryMenu'
                    and (state.get('menu', {}).get('cursor') or {}).get('count') == 0):
                drained = drain_pending(client, seconds=1)
                observed = drained.get('state') or {}
                if (drained.get('safe_to_cleanup') is True
                        and client._owned_guarded_finish_state(observed, 'materials')
                        and client.park_near(observed)):
                    client.finish()  # Once, already parked; not a fallback navigation.
                    owner.book['pending']['handoff'] = 'owned_terminal_already_parked_finish_once'
                    owner.save()
                    return
            if time.monotonic() - last_saved >= 5:
                owner.book['pending']['waiting_observation'] = {
                    key: state.get(key) for key in ('time', 'world_session', 'control_revision',
                                                   'last_request', 'phase', 'health', 'guard_busy')}
                owner.save()
                last_saved = time.monotonic()
            time.sleep(.25)


def compact(result):
    profile=result.get('profile')or{};batches=result.get('batches')or[]
    total=len(profile.get('regions',[]));cursor=result.get('cursor',0)
    return {k:v for k,v in {'phase':result.get('phase'),'reason':result.get('reason',result.get('detail','')),
        'cursor':cursor,'total_regions':total,'placed_verified':sum(r.get('placed_verified',0) for r in batches),
        'coverage_complete':result.get('coverage_complete',False),'pending_stage':(result.get('pending')or{}).get('stage'),
        'worker_running':result.get('worker_running'),'journal':result.get('journal'),'ai_calls':result.get('ai_calls',0)}.items() if v is not None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, default=Path('/Applications/.minecraft/versions/26.1.2'))
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--verbose',action='store_true',help='Print full original journal; default emits a compact status')
    parser.add_argument('action', choices=('run', 'resume', 'audit', 'status', 'pause', 'stop', 'reconcile-travel', 'reconcile-entity', 'reconcile-guard'))
    parser.add_argument('--auto-supply',action='store_true',help='缺火把时调用原生材料任务，验证后继续')
    parser.add_argument('--torch-target',type=int,default=128)
    parser.add_argument('--max-supplies',type=int,default=32)
    args = parser.parse_args(argv)
    try:
        worker = RegionsWorker(args.game_dir / 'config/twob2tkit/automation', _read(args.profile), args.out)
        if args.auto_supply:
            if args.action!='resume':raise ValueError('Automatic supply is only available for resume')
            from lighting_supply_workflow import LightingSupplyWorkflow
            workflow=LightingSupplyWorkflow(lambda:RegionsWorker(args.game_dir/'config/twob2tkit/automation',_read(args.profile),args.out),
                                            target=args.torch_target,max_supplies=args.max_supplies)
            value=workflow.run(); result=compact(value.get('lighting_result') or worker.status())
            result.update(workflow_phase=value['phase'],supplies_completed=len(value['supplies']),pending_supply=bool(value.get('pending')))
            print(json.dumps(result,ensure_ascii=False));return 2 if value['phase']=='waiting' else 0
        from lighting_entity_reconcile import reconcile as reconcile_entity, GUARD_ERROR
        result = (reconcile_entity(worker,allowed_error=GUARD_ERROR) if args.action=='reconcile-guard' else reconcile_entity(worker) if args.action == 'reconcile-entity' else worker.reconcile_travel() if args.action == 'reconcile-travel' else worker.status() if args.action == 'status' else worker.command(args.action)
                  if args.action in ('pause', 'stop') else worker.run(resume=args.action == 'resume', audit_only=args.action == 'audit'))
        print(json.dumps(result if args.verbose else compact(result), ensure_ascii=False))
        return 0 if result.get('phase') not in ('waiting', 'waiting_materials', 'waiting_unresolved', 'audited_with_remaining_risk') else 2
    except (RuntimeError, ValueError, OSError, KeyError) as error:
        print(json.dumps({'phase': 'waiting', 'detail': str(error), 'ai_calls': 0}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
