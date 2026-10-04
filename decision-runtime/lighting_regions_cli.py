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
    def __init__(self, root, profile, out=None, *, observer=None, batch=None, work_baseline=None, audit_prefix=None):
        self.root, self.profile = Path(root), validate_profile(profile)
        self.work_baseline = Path(work_baseline) if work_baseline is not None else None
        self.audit_prefix = Path(audit_prefix) if audit_prefix is not None else None
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
        selection = self.book.get('work_selection') or {}
        if selection.get('campaign') == self.book.get('campaign'):
            from lighting_work_baseline import identity
            if identity(state) != selection.get('identity'):
                raise RegionsPaused('Directed-work baseline player/projection identity changed')
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

    def reconcile_known_travel(self, *, travel_evidence=None, process_probe=None):
        from lighting_known_travel_reconcile import reconcile
        return reconcile(self,travel_evidence,process_probe=process_probe)

    def _parked_observation(self, *, expected_world=None):
        current=self.observer();require_unlocked(self.root,current)
        lease=current.get('supervision_lease')or{};task=current.get('material_task')or{}
        position=current.get('pos');movement=self.profile['movement_bounds']
        if (type(current.get('time'))is not int or not -1000<=time.time()*1000-current['time']<=3000
                or current.get('connected')is not True or not current.get('world_session')
                or expected_world is not None and current.get('world_session')!=expected_world
                or server_key(current.get('server'))!=self.profile['server']
                or current.get('dimension')!=self.profile['dimension'] or current.get('manual_movement')is not False
                or current.get('health')!=20 or current.get('food',0)<18 or current.get('screen')
                or current.get('under_water')is not False or current.get('guard_armed')is not True
                or current.get('guard_pve_only')is not True or current.get('flight')is not True
                or lease.get('kind')!='parking' or lease.get('world_session')!=current.get('world_session')
                or lease.get('revision')!=current.get('control_revision') or lease.get('remote_finish')!='guard'
                or type(current.get('control_revision'))is not int
                or task.get('process_alive')is not False or task.get('occupied')is not False
                or task.get('cancelling')is not False or current.get('native_task_session')
                or current.get('pending_scan') or current.get('phase') not in ('parking','done','waiting','stopped','error')
                or current.get('build_job',{}).get('active') or current.get('professional_printer',{}).get('enabled')
                or any(current.get(k) for k in ('borer_active','planter_active','feeder_active','fisher_active',
                'chopping','navigating','printing','native_material_busy','guard_busy'))
                or not isinstance(position,list) or len(position)!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in position)
                or any(not movement['min'][i]<=position[i]<=movement['max'][i]+1 for i in range(3))):
            raise RegionsPaused('Fresh healthy guarded parking, world or human control is unconfirmed')
        if self.control.exists() and _read(self.control).get('id')!=self.book.get('last_control'):
            raise RegionsPaused('A new human stop control remains pending')
        mailbox=self.root/'request.json'
        if mailbox.exists() and _read(mailbox).get('id')!=current.get('last_request'):
            raise RegionsPaused('An unacknowledged native request remains in flight')
        return current

    def reconcile_opening(self):
        """Archive only one proven read-only unloaded opening scan; no replay."""
        with self.worker_lock():
            raw_book=self.path.read_bytes()
            if json.loads(raw_book)!=self.book:raise RegionsPaused('Original journal changed')
            pending=deepcopy(self.book.get('pending'))
            allowed={'region_index','mode','directory','stage','error','uncertain_request'}
            if (not isinstance(pending,dict) or set(pending)!=allowed
                    or pending.get('stage')!='before_native_control' or pending.get('mode')!='lighting'
                    or pending.get('uncertain_request') is not None
                    or pending.get('error')!='LightingBlocked: Complete loaded detailed scan unavailable'
                    or type(pending.get('region_index'))is not int or pending['region_index']!=self.book['cursor']):
                raise RegionsPaused('Only the exact pre-controller unloaded survey may be reconciled')
            index=pending['region_index']
            if not 0<=index<len(self.profile['regions']):raise RegionsPaused('Original region index changed')
            directory=Path(pending['directory'])
            expected=self.out/'batch-'/f"{self.book['dispatch_sequence']:05d}"
            if directory.resolve()!=expected.resolve() or directory.is_symlink():
                raise RegionsPaused('Original batch directory differs')
            event_path=directory/'opening-survey/events.jsonl'
            files=[p for p in directory.rglob('*') if p.is_file() or p.is_symlink()]
            if files!=[event_path] or any(p.is_symlink() for p in directory.rglob('*')):
                raise RegionsPaused('Opening batch includes another intent, manifest, receipt or mutation')
            raw_events=event_path.read_bytes()
            if len(raw_events)>1024*1024:raise RegionsPaused('Opening journal exceeds bounded read')
            events=[json.loads(row) for row in raw_events.splitlines() if row.strip()]
            if len(events)!=1:raise RegionsPaused('Exactly one original read-only scan is required')
            event=events[0];rid=event.get('request_id','')
            if (not isinstance(rid,str) or not 1<=len(rid)<=96
                    or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in rid)):
                raise RegionsPaused('Original scan request identity is invalid')
            region=self.profile['regions'][index]
            px=math.floor((region['min'][0]+region['max'][0])/2+.5)
            pz=math.floor((region['min'][2]+region['max'][2])/2+.5)
            detail=f'scan stopped; partial records retained: Server chunk is not loaded: {px} {pz}'
            revision=event.get('revision_before');world=event.get('world_session')
            if (event.get('op')!='scan' or event.get('phase')!='waiting' or event.get('detail')!=detail
                    or event.get('params')!={'min':[px,-64,pz],'max':[px,319,pz],'details':True}
                    or type(revision)is not int or revision<0 or event.get('revision_after')!=revision
                    or not world or world!=self.book.get('world_session')
                    or event.get('inventory_delta')!={} or event.get('position_before')!=event.get('position_after')
                    or event.get('health_before')!=20 or event.get('health_after')!=20):
                raise RegionsPaused('Original opening scan has unknown control or mutation evidence')
            reply_path=self.root/('reply-'+rid+'.json')
            raw_reply=reply_path.read_bytes()
            if reply_path.is_symlink() or len(raw_reply)>8*1024*1024:
                raise RegionsPaused('Original native reply is unavailable or exceeds bound')
            reply=json.loads(raw_reply);scan=reply.get('pending_scan')or{}
            if (any(type(reply.get(k))is not int for k in ('control_revision','scan_start_revision','scan_end_revision','scan_cells_read','scan_total_cells'))
                    or any(type(scan.get(k))is not int for k in ('control_revision','cells_read','total_cells'))
                    or reply.get('id')!=rid or reply.get('world_session')!=world or reply.get('phase')!='waiting'
                    or reply.get('detail')!=detail or reply.get('control_revision')!=revision
                    or reply.get('scan_start_revision')!=revision or reply.get('scan_end_revision')!=revision
                    or reply.get('scan_cells_read')!=0 or reply.get('scan_total_cells')!=384
                    or reply.get('blocks')!=[] or reply.get('scan_coherent')is not False
                    or scan.get('id')!=rid or scan.get('world_session')!=world or scan.get('control_revision')!=revision
                    or scan.get('cells_read')!=0 or scan.get('total_cells')!=384 or scan.get('reading_complete')is not False):
                raise RegionsPaused('Exact native unloaded zero-cell terminal reply is unconfirmed')
            current=self._parked_observation(expected_world=world)
            if current['control_revision']<revision:raise RegionsPaused('Original control revision is unavailable')
            if self.path.read_bytes()!=raw_book or event_path.read_bytes()!=raw_events or reply_path.read_bytes()!=raw_reply:
                raise RegionsPaused('Original evidence changed during reconciliation')
            archive=self.out/'opening-reconciliations'/(rid+'-'+str(current['time']))
            archive.mkdir(parents=True,exist_ok=True)
            preserved={'original-regions.json':raw_book,'original-events.jsonl':raw_events,'original-reply.json':raw_reply,
                'current-parking.json':json.dumps(current,ensure_ascii=False,indent=2).encode()}
            for name,data in preserved.items():
                target=archive/name
                if target.exists() and target.read_bytes()!=data:raise RegionsPaused('Archived original evidence differs')
                if not target.exists():target.write_bytes(data)
            record={'outcome':'opening_unloaded_scan_preserved_read_only','original_scan_completed':False,
                'region_completed':False,'request_replayed':False,'original_pending':pending,'archive':str(archive),
                'evidence_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in preserved.items()},
                'observed_at':current['time'],'world_session':world,'cursor_preserved':index}
            previous=self.book;self.book=deepcopy(previous)
            self.book.setdefault('pending_reconciliations',[]).append(record)
            self.book.update(pending=None,phase='waiting_resume',last_revision=None,parking_lease=None,
                reason='Old unloaded scan remains incomplete; new loaded survey required before continuing')
            try:self.save()
            except BaseException:
                self.book=previous;raise
        return self.status()

    def reconcile_network_travel(self, *, network_evidence=None, process_probe=None):
        """Keep an ended-world air navigation unknown; permit a fresh route only."""
        if (self.book.get('pending')or{}).get('mode')=='audit':
            if (self.book['pending'].get('error')==
                    'RegionsPaused: Preload native navigation exceeds the thirty-two-block leg bound'):
                return self.reconcile_audit_preflight_stop(stop_evidence=network_evidence,process_probe=process_probe)
            return self.reconcile_audit_worker_stop(stop_evidence=network_evidence,process_probe=process_probe)
        import subprocess
        from lighting_cli import later_torch_frame,point
        with self.worker_lock():
            raw_book=self.path.read_bytes()
            if json.loads(raw_book)!=self.book:raise RegionsPaused('Original journal changed')
            pending=deepcopy(self.book.get('pending'));native=(pending or {}).get('uncertain_request')or{}
            if (not isinstance(pending,dict) or pending.get('stage') not in ('travel','lighting')
                    or pending.get('mode')!='lighting' or type(pending.get('region_index'))is not int
                    or pending.get('region_index')!=self.book['cursor']
                    or native!=pending.get('native_request') or native.get('op')!='navigate'
                    or pending.get('handoff')!='world_manual_or_lease_changed'):
                raise RegionsPaused('Only the exact ended-world air navigation may be reconciled')
            world,task,lease=pending.get('world_session'),pending.get('task_session'),pending.get('lease')
            rid=native.get('request_id','');directory=Path(pending['directory'])
            if (not all(isinstance(v,str) and 1<=len(v)<=96 and all(c.isalnum()or c in '_-' for c in v)
                        for v in (world,task,lease,rid))
                    or directory.resolve()!=(self.out/'batch-'/f"{self.book['dispatch_sequence']:05d}").resolve()
                    or world!=self.book.get('world_session')):
                raise RegionsPaused('Original scope or directory differs')
            evidence={}
            def read(path,lines=False):
                path=Path(path);raw=path.read_bytes()
                if path.is_symlink() or len(raw)>8*1024*1024:raise RegionsPaused('Bounded original evidence unavailable')
                evidence[path]=raw
                return [json.loads(row) for row in raw.splitlines() if row.strip()] if lines else json.loads(raw)
            request=read(directory/'network-navigation-request.json')
            if (request.get('id')!=rid or request.get('op')!='navigate' or request.get('air_only')is not True
                    or request.get('world_session')!=world or request.get('task_session')!=task
                    or native.get('world_session')!=world or native.get('task_session')!=task or native.get('lease_id')!=lease
                    or request.get('expected_revision')!=native.get('base_revision')
                    or native.get('expected_revision')!=native.get('base_revision',-2)+1
                    or request.get('dimension')!=self.profile['dimension']
                    or server_key(request.get('server'))!=self.profile['server']):
                raise RegionsPaused('Exact original air-only request is unavailable')
            allowed_request={'id','op','server','dimension','site','world_session','expected_revision','expires_at','task_session','background_ok','target','arrival','seconds','air_only'}
            movement=self.profile['movement_bounds']
            if set(request)-allowed_request or type(request.get('expected_revision'))is not int:
                raise RegionsPaused('Original navigation envelope includes another mutation')
            for key in ('site','target'):
                position=request.get(key)
                if (not isinstance(position,list) or len(position)!=3
                        or any(type(v)not in (int,float) or not math.isfinite(v) for v in position)
                        or any(not movement['min'][i]<=position[i]<=movement['max'][i]+1 for i in range(3))):
                    raise RegionsPaused('Original navigation scope is outside authorization')
            manifest=read(directory/('run-manifest-'+task+'.json'))
            plan=read(directory/'arrival-height-plan.json');baseline=plan.get('actual_column')or{}
            if (manifest.get('task_session')!=task or manifest.get('world_session')!=world
                    or manifest.get('dimension')!=self.profile['dimension'] or manifest.get('complete')is not False
                    or manifest.get('server_hash')!=hashlib.sha256(str(baseline.get('server')).encode()).hexdigest()[:16]
                    or baseline.get('world_session')!=world or baseline.get('phase')!='done'
                    or type(baseline.get('health'))not in (int,float) or not math.isfinite(baseline['health'])
                    or baseline['health']<18 or baseline.get('connected')is not True
                    or server_key(baseline.get('server'))!=self.profile['server']):
                raise RegionsPaused('Original owned manifest or starting inventory differs')
            events=read(directory/'events.jsonl',True)
            first=(events or [{}])[0]
            if (first.get('op')!='material_session' or first.get('params',{}).get('supervision_lease')!=lease
                    or first.get('params',{}).get('task_session')!=task):
                raise RegionsPaused('Original native lease is unconfirmed')
            reply_path=self.root/('reply-'+rid+'.json');reply=None
            if reply_path.exists():
                reply=read(reply_path)
                if (reply.get('id')!=rid or reply.get('world_session')!=world or reply.get('phase') not in ('waiting','stopped')
                        or reply.get('detail') not in ('air-only path changed; no blocks were excavated','World changed; task stopped')):
                    raise RegionsPaused('Original navigation reply is not a known interrupted outcome')
            prefix=events
            if events and events[-1].get('request_id')==rid:
                if reply is None or events[-1].get('phase')!=reply.get('phase') or events[-1].get('detail')!=reply.get('detail'):
                    raise RegionsPaused('Original interrupted event lacks its exact native reply')
                prefix=events[:-1]
            allowed={'material_session','scan','snapshot','navigate','select_item','interact','material_job_park'}
            if (not prefix or any(e.get('world_session')!=world or e.get('params',{}).get('task_session')!=task
                    or e.get('op') not in allowed or e.get('request_id')==rid
                    or not isinstance(e.get('inventory_delta'),dict)
                    or e.get('phase') not in ((None,'done') if e.get('op')=='snapshot' else ('done',)) for e in prefix)
                    or prefix[-1].get('revision_after')!=request['expected_revision']
                    or type(prefix[-1].get('health_after'))not in (int,float)
                    or not math.isfinite(prefix[-1]['health_after']) or prefix[-1]['health_after']<18):
                raise RegionsPaused('Original settled prefix contains an unknown action or health exit')
            opening=read(directory/'opening-survey/events.jsonl',True)
            region=self.profile['regions'][pending['region_index']]
            px=math.floor((region['min'][0]+region['max'][0])/2+.5);pz=math.floor((region['min'][2]+region['max'][2])/2+.5)
            if (len(opening)!=1 or opening[0].get('op')!='scan' or opening[0].get('phase')!='done'
                    or opening[0].get('world_session')!=world or opening[0].get('request_id')!=baseline.get('id')
                    or opening[0].get('params')!={'min':[px,-64,pz],'max':[px,319,pz],'details':True}
                    or opening[0].get('inventory_delta')!={} or baseline.get('scan_cells_read')!=384
                    or baseline.get('scan_total_cells')!=384):
                raise RegionsPaused('Original opening survey has a mutation or incomplete scan')
            placements=[];report_path=directory/'report.json'
            if report_path.exists():
                report=read(report_path);placements=report.get('placed')
                if (pending['stage']!='lighting' or report.get('world_session')!=world or report.get('task_session')!=task
                        or not isinstance(placements,list) or len(placements)>self.profile['batch_torches']):
                    raise RegionsPaused('Original partial placement report is invalid')
            interactions={e['request_id']:e for e in prefix if e.get('op')=='interact'}
            if len(interactions)!=len(placements):raise RegionsPaused('An original torch interaction remains unknown')
            baseline_stock=stock(baseline);seen=set()
            for index,placed in enumerate(placements):
                target=point(placed.get('target'));interaction=placed.get('interaction_request')
                before=read(directory/f'inventory-before-{index}.json')
                response=read(directory/f'interaction-{index}.json')
                if (target in seen or placed.get('world_session')!=world or placed.get('task_session')!=task
                        or placed.get('state')!='verified' or placed.get('before_stock')!=baseline_stock-index
                        or placed.get('after_stock')!=placed.get('before_stock',0)-1 or stock(before)!=placed['before_stock']
                        or before.get('time')!=placed.get('before_time') or before.get('world_session')!=world
                        or (before.get('supervision_lease')or{}).get('id')!=lease
                        or (before.get('supervision_lease')or{}).get('job_session')!=task
                        or (before.get('supervision_lease')or{}).get('world_session')!=world or interaction not in interactions
                        or response.get('id')!=interaction or response.get('world_session')!=world or response.get('phase')!='done'
                        or (response.get('supervision_lease')or{}).get('id')!=lease
                        or (response.get('supervision_lease')or{}).get('job_session')!=task
                        or (response.get('supervision_lease')or{}).get('world_session')!=world):
                    raise RegionsPaused('Original placement intent or interaction receipt is unconfirmed')
                support=point(placed.get('support'));params=interactions[interaction].get('params')or{}
                if (target!=(support[0],support[1]+1,support[2]) or params.get('pos')!=list(support)
                        or params.get('face')!='up' or params.get('expected_hand')!='minecraft:torch'
                        or not isinstance(params.get('expected_state'),str)):
                    raise RegionsPaused('Original interaction does not match the exact torch intent')
                last=placed['before_time']
                for frame in (1,2):
                    actual=read(directory/f'actual-torch-{index}-frame-{frame}.json')
                    inventory=read(directory/f'inventory-after-{index}-frame-{frame}.json')
                    owned=inventory.get('supervision_lease')or{}
                    if (owned.get('id')!=lease or owned.get('job_session')!=task or owned.get('world_session')!=world
                            or not later_torch_frame(actual,inventory,target,world,placed['before_stock'],last)):
                        raise RegionsPaused('Original two-frame torch witness differs')
                    last=inventory['time']
                if last!=placed.get('after_time'):raise RegionsPaused('Original final placement time differs')
                key=hashlib.sha256((world+':'+','.join(map(str,target))).encode()).hexdigest()
                if read(self.root/'lighting-intents'/(key+'.json'))!=placed:
                    raise RegionsPaused('Original durable torch intent differs')
                seen.add(target)
            intents=[]
            for path in (self.root/'lighting-intents').glob('*.json'):
                value=json.loads(path.read_bytes())
                if value.get('world_session')==world and value.get('task_session')==task:intents.append(value)
            if len(intents)!=len(placements) or any(value not in placements for value in intents):
                raise RegionsPaused('An original durable placement is unresolved')
            if (sum(e.get('inventory_delta',{}).get('minecraft:torch',0) for e in prefix)!=-len(placements)
                    or any(e.get('inventory_delta')!=({'minecraft:torch':-1} if e.get('op')=='interact' else {}) for e in prefix)
                    or any(directory.rglob('inflight.json'))):
                raise RegionsPaused('Original inventory mutation or inflight outcome differs')
            record_path=Path(network_evidence) if network_evidence else self.out/('network-disconnect-evidence-'+rid+'.json')
            network=read(record_path)
            if (network.get('reason')!='连接超时' or network.get('request_id')!=rid or network.get('world_session')!=world
                    or network.get('task_session')!=task or network.get('health_exit')is not False
                    or not str(network.get('last_disconnect_log','')).endswith('Client disconnected with reason: 连接超时')
                    or network.get('last_owned_health')!=prefix[-1].get('health_after')
                    or network.get('original_request_sha256')!=hashlib.sha256(evidence[directory/'network-navigation-request.json']).hexdigest()
                    or network.get('worker_exit_code')!=2 or network.get('worker_process_alive')is not False):
                raise RegionsPaused('Exact saved network timeout or dead worker evidence is unavailable')
            if process_probe is None:
                pattern=r'[k]it_cli\.py.* lighting resume( |$)|[l]ighting_regions_cli\.py.* resume( |$)'
                probe=subprocess.run(['/usr/bin/pgrep','-f',pattern],capture_output=True,text=True)
                if probe.returncode not in (0,1):raise RegionsPaused('Cannot determine worker process state')
                alive=probe.returncode==0
            else:alive=process_probe()
            if alive is not False:raise RegionsPaused('A lighting worker process is still alive')
            current=self._parked_observation()
            if current.get('world_session')==world or stock(current)!=baseline_stock-len(placements):
                raise RegionsPaused('Fresh new-world torch inventory conservation is unconfirmed')
            if any(path.read_bytes()!=raw for path,raw in evidence.items()) or self.path.read_bytes()!=raw_book:
                raise RegionsPaused('Original network evidence changed')
            archive=self.out/'network-reconciliations'/(rid+'-'+str(current['time']));archive.mkdir(parents=True,exist_ok=True)
            preserved={'original-regions.json':raw_book,'current-parking.json':json.dumps(current,ensure_ascii=False,indent=2).encode()}
            for path,raw in evidence.items():
                relative=path.relative_to(directory) if path.is_relative_to(directory) else Path('external')/path.name
                preserved[str(relative)]=raw
            for name,data in preserved.items():
                target=archive/name;target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists() and target.read_bytes()!=data:raise RegionsPaused('Archived evidence differs')
                if not target.exists():target.write_bytes(data)
            record={'outcome':'previous_network_navigation_unknown','navigation_completed':False,'request_replayed':False,
                'region_completed':False,'original_pending':pending,'archive':str(archive),'partial_placed_verified':len(placements),
                'original_reply':'missing' if reply is None else 'known_interrupted','observed_at':current['time'],
                'previous_world_session':world,'world_session':current['world_session'],
                'evidence_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in preserved.items()}}
            previous=self.book;self.book=deepcopy(previous)
            self.book.setdefault('pending_reconciliations',[]).append(record)
            if placements:
                if any(b.get('directory')==str(directory) for b in self.book['batches']):
                    self.book=previous;raise RegionsPaused('Original partial placement has already been counted')
                self.book['batches'].append({'directory':str(directory),'region_index':pending['region_index'],
                    'campaign':self.book['campaign'],'mode':'lighting','partial_verified':True,'placed_verified':len(placements),
                    'region_completed':False,'eligible_remaining':None})
            self.book.update(pending=None,phase='waiting_resume',last_revision=None,parking_lease=None,
                reason='Previous network navigation remains unknown; fresh route from current pose required')
            try:self.save()
            except BaseException:
                self.book=previous;raise
        return self.status()

    def reconcile_audit_preflight_stop(self,*,stop_evidence=None,process_probe=None):
        """Archive one proved local navigation rejection before native dispatch."""
        import subprocess
        with self.worker_lock():
            raw_book=self.path.read_bytes();pending=deepcopy(self.book.get('pending'));native=(pending or{}).get('uncertain_request')or{}
            if (json.loads(raw_book)!=self.book or not isinstance(pending,dict)
                or pending.get('error')!='RegionsPaused: Preload native navigation exceeds the thirty-two-block leg bound'
                or pending.get('mode')!='audit'or pending.get('stage')!='travel'or pending.get('travel_stage')!='preload'
                or self.book['cursor']!=len(self.profile['regions'])or pending.get('region_index')!=len(self.book['audits'])
                or native!=pending.get('native_request')or native.get('op')!='scan'):
                raise RegionsPaused('Only the exact known audit navigation-bound preflight may be archived')
            world,task,lease,rid=pending['world_session'],pending['task_session'],pending['lease'],native.get('request_id')
            if (not all(isinstance(v,str)and 1<=len(v)<=96 and all(c.isalnum()or c in '_-'for c in v)for v in (world,task,lease,rid))
                or world!=self.book['world_session']or native.get('world_session')!=world
                or native.get('task_session')!=task or native.get('lease_id')!=lease
                or type(native.get('base_revision'))is not int or native.get('expected_revision')!=native['base_revision']):
                raise RegionsPaused('Known audit preflight owner or read revision differs')
            directory=Path(pending['directory'])
            if directory.resolve()!=(self.out/'audit-'/f"{self.book['dispatch_sequence']:05d}").resolve():
                raise RegionsPaused('Original audit directory differs')
            evidence={}
            def read(path,lines=False):
                path=Path(path);raw=path.read_bytes()
                if path.is_symlink()or len(raw)>8*1024*1024:raise RegionsPaused('Bounded preflight evidence unavailable')
                evidence[path]=raw
                return [json.loads(v)for v in raw.splitlines()if v.strip()]if lines else json.loads(raw)
            if stop_evidence is None:raise RegionsPaused('Explicit graceful preflight stop evidence is required')
            stopped=read(stop_evidence);saved=Path(stop_evidence).parent
            before=read(saved/'before.json');after=read(saved/'after-observation.json')
            original=read(saved/'original-pending.json');reply=read(saved/'original-scan-reply.json')
            keep=read(self.root/('supervision-receipt-'+lease+'.json'))
            if reply!=read(self.root/('reply-'+rid+'.json')):raise RegionsPaused('Original exact scan copies differ')
            core=('region_index','mode','directory','stage','travel_stage','world_session','task_session','lease',
                  'preload_leg','native_request','uncertain_request','error')
            if any(original.get(k)!=pending.get(k)for k in core):raise RegionsPaused('Preserved original pending scope differs')
            events=read(directory/'events.jsonl',True);opening=read(directory/'opening-survey/events.jsonl',True)
            manifest=read(directory/('run-manifest-'+task+'.json'));plan=read(directory/'preload-route.json')
            sessions=[e for e in events if e.get('op')=='material_session']
            if (len(sessions)!=1 or sessions[0].get('params',{}).get('task_session')!=task
                or sessions[0].get('params',{}).get('supervision_lease')!=lease
                or manifest.get('task_session')!=task or manifest.get('world_session')!=world or manifest.get('complete')is not False
                or plan.get('world_session')!=world or plan.get('task_session')!=task):
                raise RegionsPaused('Original audit session or preload plan differs')
            for event in events+opening:
                params=event.get('params')or{}
                if (event.get('op')not in ('scan','snapshot','material_session','navigate')or event.get('world_session')!=world
                    or event.get('inventory_delta')!={}or event.get('health_before')!=20 or event.get('health_after')!=20
                    or event.get('phase')not in ((None,'done')if event.get('op')=='snapshot'else('done',))
                    or event.get('op')!='scan'and params.get('task_session')!=task
                    or event.get('op')=='scan'and params.get('task_session')not in (None,task)
                    or event.get('op')=='navigate'and params.get('air_only')is not True):
                    raise RegionsPaused('Original preflight prefix has unknown work, interaction or inventory mutation')
            exact=[e for e in events if e.get('request_id')==rid]
            if len(exact)!=1 or exact[0]!=events[-1]or exact[0].get('op')!='scan':
                raise RegionsPaused('Last original event is not the exact terminal scan')
            params=exact[0]['params'];low,high=bounds(params.get('min'),params.get('max'))
            total=math.prod(b-a+1 for a,b in zip(low,high));revision=native['base_revision']
            if (params.get('details')is not True or reply.get('id')!=rid or reply.get('phase')!='done'
                or reply.get('world_session')!=world or reply.get('control_revision')!=revision
                or any(reply.get(k)!=revision for k in ('scan_start_revision','scan_end_revision'))
                or reply.get('scan_cells_read')!=total or reply.get('scan_total_cells')!=total
                or exact[0].get('revision_before')!=revision or exact[0].get('revision_after')!=revision
                or before.get('last_request')!=rid or before.get('control_revision')!=revision or before.get('pending_scan')
                or any((before.get('supervision_lease')or{}).get(k)!=v for k,v in
                       (('id',lease),('job_session',task),('world_session',world),('revision',revision),('kind','materials')))):
                raise RegionsPaused('Original terminal full scan or idle materials owner is unconfirmed')
            scan_cells(reply,low,high,world)
            unknown=[row for leg in plan.get('legs',[])for row in leg.get('route',[])if row.get('phase')=='unknown']
            if (len(unknown)!=1 or unknown[0].get('request_id')is not None or unknown[0].get('native_inflight')is not None
                or unknown[0].get('request_before')!=rid or unknown[0].get('world_session')!=world
                or not isinstance(unknown[0].get('target'),list)or len(unknown[0]['target'])!=3
                or any(type(v)not in(int,float)or not math.isfinite(v)for v in unknown[0]['target'])
                or math.dist(reply['pos'],unknown[0]['target'])<=32.000001):
                raise RegionsPaused('Exact locally rejected navigation was dispatched or lacks its bound witness')
            if (stopped.get('signal')!='SIGINT'or stopped.get('reason')!='known_pre_dispatch_bound_rejection_after_exact_terminal_read'
                or stopped.get('request_replayed')is not False or type(stopped.get('pid'))is not int or stopped['pid']<1
                or type(stopped.get('time'))is not int or not before['time']<=stopped['time']<=after['time']
                or (directory/'report.json').exists()or (directory/'current-region-audit.json').exists()
                or any(directory.rglob('inflight.json'))):
                raise RegionsPaused('Graceful idle worker stop or absence of original audit mutation is unconfirmed')
            for path in (self.root/'lighting-intents').glob('*.json'):
                value=read(path)
                if value.get('world_session')==world and value.get('task_session')==task:
                    raise RegionsPaused('An original audit placement intent exists')
            if process_probe is None:
                probe=subprocess.run(['/bin/kill','-0',str(stopped['pid'])],capture_output=True,text=True)
                alive=probe.returncode==0
            else:alive=process_probe()
            if alive is not False:raise RegionsPaused('The old audit worker is still alive')
            current=self._parked_observation(expected_world=world)
            for frame in (before,reply,after,current):
                owned=frame.get('supervision_lease')or{}
                if (frame.get('connected')is not True or frame.get('health')!=20 or frame.get('food',0)<18
                    or frame.get('world_session')!=world or frame.get('manual_movement')is not False or frame.get('screen')
                    or frame.get('guard_armed')is not True or frame.get('guard_pve_only')is not True or frame.get('flight')is not True
                    or frame.get('navigating')or frame.get('native_material_busy')or frame.get('guard_busy')
                    or frame.get('pending_scan')and frame is not reply
                    or (frame.get('safety_hold')or{}).get('active')or stock(frame)!=stock(reply)
                    or server_key(frame.get('server'))!=self.profile['server']or frame.get('dimension')!=self.profile['dimension']
                    or not reply.get('player_uuid')or frame.get('player_uuid')!=reply['player_uuid']
                    or frame.get('projection_selection')!=reply.get('projection_selection')
                    or owned.get('id')!=lease or owned.get('job_session')!=task or owned.get('world_session')!=world):
                    raise RegionsPaused('Original idle read or current same-owner survival/identity changed')
            for frame in (after,current):
                owned=frame['supervision_lease'];safety=frame.get('supervision_safety')or{};keys=frame.get('movement_keys')or{}
                if (owned.get('kind')!='parking'or owned.get('revision')!=frame.get('control_revision')
                    or frame.get('control_revision')!=revision+1 or safety.get('action')!='KEEP_PVE_GUARD'
                    or safety.get('cause')!='heartbeat_lost'or safety.get('lease')!=lease or safety.get('job_session')!=task
                    or keep.get('lease')!=lease or keep.get('job_session')!=task or keep.get('action')!='KEEP_PVE_GUARD'
                    or keep.get('cause')!='heartbeat_lost'or type(keep.get('time'))is not int or keep['time']<stopped['time']
                    or safety.get('time')!=keep['time']or owned.get('parked_at')!=keep['time']
                    or not keys or any(v is not False for v in keys.values())
                    or math.dist(frame['pos'],owned['park_target'])>.6):
                    raise RegionsPaused('Exact same-owner native PARK/KEEP after worker stop is unconfirmed')
            if any(path.read_bytes()!=raw for path,raw in evidence.items())or self.path.read_bytes()!=raw_book:
                raise RegionsPaused('Original known-preflight evidence changed')
            archive=self.out/'audit-preflight-reconciliations'/(rid+'-'+str(current['time']));archive.mkdir(parents=True,exist_ok=True)
            preserved={'original-regions.json':raw_book,'current-parking.json':json.dumps(current,ensure_ascii=False,indent=2).encode()}
            for path,raw in evidence.items():
                name=path.relative_to(directory)if path.is_relative_to(directory)else Path('external')/path.name
                if str(name)in preserved and preserved[str(name)]!=raw:raise RegionsPaused('Preflight archive filename collision')
                preserved[str(name)]=raw
            for name,raw in preserved.items():
                target=archive/name;target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists()and target.read_bytes()!=raw:raise RegionsPaused('Archived original preflight differs')
                if not target.exists():target.write_bytes(raw)
            record={'outcome':'known_audit_navigation_predispatch_rejection_preserved','original_scan_completed':True,
                'navigation_dispatched':False,'audit_completed':False,'region_completed':False,'request_replayed':False,
                'original_pending':pending,'archive':str(archive),'world_session':world,'observed_at':current['time'],
                'cursor_preserved':self.book['cursor'],'evidence_sha256':{name:hashlib.sha256(raw).hexdigest()for name,raw in preserved.items()}}
            previous=self.book;self.book=deepcopy(previous);self.book.setdefault('pending_reconciliations',[]).append(record)
            self.book.update(pending=None,phase='waiting_resume',last_revision=None,parking_lease=None,coverage_complete=False,
                             reason='Known local navigation preflight archived; fresh complete audit required')
            try:self.save()
            except BaseException:self.book=previous;raise
        return self.status()

    def reconcile_audit_worker_stop(self,*,stop_evidence=None,process_probe=None):
        """Preserve one unknown audit preload scan after an ended game/worker.

        Every earlier action must be terminal air travel or a read. This never
        credits an audit, retries the missing read, or changes completed work.
        """
        import subprocess
        with self.worker_lock():
            raw_book=self.path.read_bytes()
            if json.loads(raw_book)!=self.book:raise RegionsPaused('Original audit journal changed')
            pending=deepcopy(self.book.get('pending'));native=(pending or{}).get('uncertain_request')or{}
            if (not isinstance(pending,dict)or pending.get('mode')!='audit'or pending.get('stage')!='travel'
                or pending.get('travel_stage')!='preload'or type(pending.get('region_index'))is not int
                or self.book['cursor']!=len(self.profile['regions'])
                or pending['region_index']!=len(self.book.get('audits',[]))
                or not 0<=pending['region_index']<len(self.profile['regions'])
                or native!=pending.get('native_request')or native.get('op')!='scan'):
                raise RegionsPaused('Only an exact unknown read-only audit preload scan may be archived')
            world,task,lease=pending.get('world_session'),pending.get('task_session'),pending.get('lease')
            rid=native.get('request_id');directory=Path(pending['directory'])
            if (not all(isinstance(v,str)and 1<=len(v)<=96 and all(c.isalnum()or c in '_-'for c in v)
                        for v in (world,task,lease,rid))
                or directory.resolve()!=(self.out/'audit-'/f"{self.book['dispatch_sequence']:05d}").resolve()
                or world!=self.book.get('world_session')):
                raise RegionsPaused('Original audit scope or directory differs')
            evidence={}
            def read(path,lines=False):
                path=Path(path);raw=path.read_bytes()
                if path.is_symlink()or len(raw)>8*1024*1024:raise RegionsPaused('Bounded audit evidence unavailable')
                evidence[path]=raw
                return [json.loads(v)for v in raw.splitlines()if v.strip()]if lines else json.loads(raw)
            marker=read(Path(stop_evidence)if stop_evidence else self.out/('audit-worker-stop-evidence-'+rid+'.json'))
            request=read(marker['original_request_path']);last=read(marker['last_status_path'])
            manifest=read(directory/('run-manifest-'+task+'.json'))
            baseline=read(directory/'current-park-column.json');plan=read(directory/'current-park-plan.json')
            events=read(directory/'events.jsonl',True);opening=read(directory/'opening-survey/events.jsonl',True)
            allowed={'id','op','server','dimension','site','world_session','expected_revision','expires_at',
                     'task_session','background_ok','min','max','details'}
            if (set(request)-allowed or request.get('id')!=rid or request.get('op')!='scan'
                or request.get('details')is not True or request.get('world_session')!=world
                or request.get('task_session')!=task or request.get('dimension')!=self.profile['dimension']
                or server_key(request.get('server'))!=self.profile['server']
                or native.get('world_session')!=world or native.get('task_session')!=task
                or native.get('lease_id')!=lease or type(request.get('expected_revision'))is not int
                or native.get('base_revision')!=request['expected_revision']
                or native.get('expected_revision')!=request['expected_revision']):
                raise RegionsPaused('Original audit request is not the exact scoped read-only scan')
            bounds(request.get('min'),request.get('max'))
            site=request.get('site');movement=self.profile['movement_bounds']
            if (not isinstance(site,list)or len(site)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in site)
                or any(not movement['min'][i]<=site[i]<=movement['max'][i]+1 for i in range(3))):
                raise RegionsPaused('Original audit scan site lies outside the authorized movement scope')
            if (manifest.get('task_session')!=task or manifest.get('world_session')!=world
                or manifest.get('complete')is not False or type(manifest.get('created_at'))is not int
                or manifest.get('dimension')!=self.profile['dimension']or manifest.get('game_mode')!='survival'
                or manifest.get('server_hash')!=hashlib.sha256(str(baseline.get('server')).encode()).hexdigest()[:16]
                or baseline.get('world_session')!=world or baseline.get('phase')!='done'
                or baseline.get('health')!=20 or baseline.get('connected')is not True
                or server_key(baseline.get('server'))!=self.profile['server']
                or baseline.get('dimension')!=self.profile['dimension']
                or baseline.get('scan_cells_read')!=baseline.get('scan_total_cells')
                or baseline.get('scan_total_cells',0)<384 or plan.get('world_session')!=world
                or not isinstance(baseline.get('player_uuid'),str)or not baseline['player_uuid']
                or manifest.get('placement_key')!=(baseline.get('projection_selection')or{}).get('key')
                or not manifest.get('placement_key')):
                raise RegionsPaused('Original full column, identity or owned audit manifest differs')
            position=baseline.get('pos');observed=plan.get('observed')or{}
            if (not isinstance(position,list)or len(position)!=3
                or any(type(v)not in(int,float)or not math.isfinite(v)for v in position)):
                raise RegionsPaused('Original opening body pose is unverified')
            column_low=[math.floor(position[0]-.35),-64,math.floor(position[2]-.35)]
            column_high=[math.floor(position[0]+.35),319,math.floor(position[2]+.35)]
            column_total=math.prod(b-a+1 for a,b in zip(column_low,column_high))
            if (len(opening)!=1 or opening[0].get('request_id')!=baseline.get('id')
                or opening[0].get('op')!='scan'or opening[0].get('phase')!='done'
                or opening[0].get('world_session')!=world or opening[0].get('inventory_delta')!={}
                or opening[0].get('params')!={'min':column_low,'max':column_high,'details':True}
                or baseline.get('scan_cells_read')!=column_total or baseline.get('scan_total_cells')!=column_total
                or observed.get('world_session')!=world or observed.get('control_revision')!=baseline.get('control_revision')
                or observed.get('pos')!=position or plan.get('park_target')!=position):
                raise RegionsPaused('Original opening column has unknown or mutating work')
            sessions=[e for e in events if e.get('op')=='material_session']
            if (len(sessions)!=1 or sessions[0].get('params',{}).get('task_session')!=task
                or sessions[0].get('params',{}).get('supervision_lease')!=lease):
                raise RegionsPaused('Original single native audit session differs')
            for e in events:
                params=e.get('params')or{}
                if (e.get('op')not in ('scan','snapshot','material_session','navigate')
                    or e.get('world_session')!=world or e.get('request_id')==rid
                    or e.get('inventory_delta')!={}or e.get('health_before')!=20 or e.get('health_after')!=20
                    or e.get('phase')not in ((None,'done')if e.get('op')=='snapshot'else('done',))
                    or e.get('op')!='scan'and params.get('task_session')!=task
                    or e.get('op')=='scan'and params.get('task_session')not in (None,task)
                    or e.get('op')=='navigate'and params.get('air_only')is not True):
                    raise RegionsPaused('Original audit prefix contains unknown movement, health loss or mutation')
            pending_scan=last.get('pending_scan')or{};original_lease=last.get('supervision_lease')or{}
            scan_total=math.prod(b-a+1 for a,b in zip(request['min'],request['max']))
            if (not events or events[-1].get('revision_after')!=request['expected_revision']
                or last.get('world_session')!=world or last.get('control_revision')!=request['expected_revision']
                or last.get('last_request')!=rid or pending_scan.get('id')!=rid
                or pending_scan.get('world_session')!=world or pending_scan.get('control_revision')!=request['expected_revision']
                or pending_scan.get('total_cells')!=scan_total or type(pending_scan.get('cells_read'))is not int
                or not 0<=pending_scan['cells_read']<scan_total or pending_scan.get('reading_complete')is not False
                or original_lease.get('kind')!='materials' or original_lease.get('id')!=lease
                or original_lease.get('job_session')!=task or original_lease.get('world_session')!=world
                or original_lease.get('revision')!=request['expected_revision']
                or last.get('health')!=20 or last.get('food',0)<18
                or last.get('manual_movement')is not False or (last.get('safety_hold')or{}).get('active')
                or stock(last)!=stock(baseline)or any(directory.rglob('inflight.json'))
                or (directory/'report.json').exists()or (self.root/('reply-'+rid+'.json')).exists()):
                raise RegionsPaused('Original audit had an unknown mutation, read reply or unsafe last observation')
            for path in (self.root/'lighting-intents').glob('*.json'):
                value=read(path)
                if value.get('world_session')==world and value.get('task_session')==task:
                    raise RegionsPaused('An original audit placement intent exists')
            if (marker.get('schema')!=1 or marker.get('reason')!='worker_and_game_not_running'
                or marker.get('request_id')!=rid or marker.get('world_session')!=world or marker.get('task_session')!=task
                or marker.get('health_exit')is not False or marker.get('previous_worker_process_alive')is not False
                or marker.get('previous_game_process_alive')is not False or type(marker.get('processes_checked_at'))is not int
                or type(last.get('time'))is not int or marker['processes_checked_at']<last['time']
                or marker.get('original_request_sha256')!=hashlib.sha256(evidence[Path(marker['original_request_path'])]).hexdigest()
                or marker.get('last_status_sha256')!=hashlib.sha256(evidence[Path(marker['last_status_path'])]).hexdigest()):
                raise RegionsPaused('Exact preserved request/status or prior stopped processes are unconfirmed')
            for path in marker.get('health_hold_paths',[]):
                hold=read(path)
                if hold.get('active')is True and (type(hold.get('time'))is not int or hold['time']>=manifest['created_at']):
                    raise RegionsPaused('A new health-safety hold cannot be archived as a worker stop')
            if process_probe is None:
                probe=subprocess.run(['/usr/bin/pgrep','-f',r'[k]it_cli\.py.* lighting (resume|audit)( |$)|[l]ighting_regions_cli\.py.* (resume|audit)( |$)'],capture_output=True,text=True)
                if probe.returncode not in (0,1):raise RegionsPaused('Cannot determine audit worker process state')
                alive=probe.returncode==0
            else:alive=process_probe()
            if alive is not False:raise RegionsPaused('An audit worker process is still alive')
            current=self._parked_observation();owned=current['supervision_lease'];safety=current.get('supervision_safety')or{}
            keys=current.get('movement_keys')or{}
            try:host=tuple(int(v)for v in current.get('kit_version','').split('.'))
            except (AttributeError,ValueError):host=()
            parked=owned.get('park_target');pose=current['pos']
            if (current.get('world_session')==world or stock(current)!=stock(baseline)
                or host<(2026,10,4,1)or not isinstance(owned.get('id'),str)or not owned['id']
                or not isinstance(owned.get('job_session'),str)or not owned['job_session']
                or owned.get('id')==lease or owned.get('job_session')==task
                or not isinstance(parked,list)or len(parked)!=3
                or any(type(v)not in(int,float)or not math.isfinite(v)for v in parked)
                or math.dist(pose,parked)>.6 or current.get('concrete',{}).get('active')
                or current.get('gravel',{}).get('active')
                or safety.get('action')!='KEEP_PVE_GUARD'or safety.get('lease')!=owned.get('id')
                or safety.get('job_session')!=owned.get('job_session')or not keys or any(v is not False for v in keys.values())
                or current.get('player_uuid')!=baseline['player_uuid']
                or current.get('game_mode')!='survival'
                or current.get('projection_selection')!=baseline.get('projection_selection')
                or server_key(last.get('server'))!=self.profile['server']or last.get('dimension')!=self.profile['dimension']
                or last.get('player_uuid')!=baseline['player_uuid']or last.get('projection_selection')!=baseline.get('projection_selection')):
                raise RegionsPaused('Fresh new-world native parking, player/projection identity or inventory differs')
            if any(path.read_bytes()!=raw for path,raw in evidence.items())or self.path.read_bytes()!=raw_book:
                raise RegionsPaused('Original audit evidence changed')
            archive=self.out/'audit-worker-stop-reconciliations'/(rid+'-'+str(current['time']));archive.mkdir(parents=True,exist_ok=True)
            preserved={'original-regions.json':raw_book,'current-parking.json':json.dumps(current,ensure_ascii=False,indent=2).encode()}
            for path,raw in evidence.items():
                name=path.relative_to(directory)if path.is_relative_to(directory)else Path('external')/path.name
                if str(name)in preserved and preserved[str(name)]!=raw:raise RegionsPaused('Archive filename collision')
                preserved[str(name)]=raw
            for name,raw in preserved.items():
                target=archive/name;target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists()and target.read_bytes()!=raw:raise RegionsPaused('Archived audit evidence differs')
                if not target.exists():target.write_bytes(raw)
            record={'outcome':'previous_audit_read_unknown_after_worker_stop','original_read_completed':False,
                'audit_completed':False,'region_completed':False,'request_replayed':False,'original_reply':'missing',
                'original_pending':pending,'archive':str(archive),'previous_world_session':world,
                'world_session':current['world_session'],'observed_at':current['time'],'cursor_preserved':self.book['cursor'],
                'evidence_sha256':{name:hashlib.sha256(raw).hexdigest()for name,raw in preserved.items()}}
            previous=self.book;self.book=deepcopy(previous)
            self.book.setdefault('pending_reconciliations',[]).append(record)
            self.book.update(pending=None,phase='waiting_resume',last_revision=None,parking_lease=None,
                coverage_complete=False,reason='Original audit read stays unknown; fresh complete audit required')
            try:self.save()
            except BaseException:self.book=previous;raise
        return self.status()

    def run(self, *, resume=False, audit_only=False):
        with self.worker_lock():
            if self.book['pending'] is not None:
                raise RegionsPaused('Original pending batch needs read-only reconciliation; no replay')
            prior_control = _read(self.control) if resume and self.control.exists() else None
            state = self.observer()
            prefix = None
            if self.audit_prefix is not None:
                if not resume and not audit_only:
                    raise ValueError('An audit prefix is only available for explicit resume/audit')
                from lighting_audit_prefix import validate as validate_prefix, no_pending
                from lighting_work_baseline import current_identity
                prefix = validate_prefix(self,self.audit_prefix,state)
                state = self.observer();current_identity(state,prefix['identity']);no_pending(self.root,state)
            directed = None
            retained = self.book.get('work_selection')
            if retained is not None and (not isinstance(retained, dict) or retained.get('schema') != 1
                    or retained.get('mode') != 'all_baseline_unprotected_dark_regions'
                    or type(retained.get('campaign')) is not int
                    or not isinstance(retained.get('identity'), dict)
                    or not isinstance(retained.get('baseline_path'), str)
                    or not isinstance(retained.get('selected_indices'), list)):
                raise RegionsPaused('Original directed-work selection metadata is incomplete; no fallback')
            retained = retained or {}
            requested = self.work_baseline
            if audit_only and requested is not None:
                raise ValueError('A work baseline cannot restrict the final full audit')
            if not audit_only:
                if resume and retained.get('campaign') == self.book.get('campaign') and requested is None:
                    requested = Path(retained['baseline_path'])
                if requested is not None:
                    from lighting_work_baseline import validate, current_identity
                    def no_pending(observed):
                        mailbox = self.root/'request.json'
                        if mailbox.exists():
                            request, last = _read(mailbox), observed.get('last_request')
                            if (not isinstance(request, dict) or not isinstance(request.get('id'), str)
                                    or not request['id'] or not isinstance(last, str) or not last
                                    or request['id'] != last or request.get('world_session') != observed.get('world_session')):
                                raise RegionsPaused('Directed work has an unacknowledged native request; preserve it')
                        for path in (self.root/'lighting-intents').glob('*.json'):
                            intent = _read(path)
                            if intent.get('world_session') == observed.get('world_session') and intent.get('state') != 'verified':
                                raise RegionsPaused('Directed work has an unresolved original torch intent; no replay')
                    no_pending(state)
                    directed = validate(requested, self.profile, self.out, state)
                    state = self.observer()
                    current_identity(state, directed['identity'])
                    no_pending(state)
                    if self.book['world_session'] not in (None, state['world_session']):
                        raise RegionsPaused('Directed work cannot resume a baseline in another world')
                    if (resume and retained.get('campaign') == self.book.get('campaign')
                            and {k:v for k,v in retained.items() if k != 'campaign'} != directed):
                        raise RegionsPaused('Original directed-work baseline changed; preserve this campaign')
            # Explicit resume may start a fresh world only when no original
            # uncertain action remains and the player-cleared safety lock passes.
            if resume or not audit_only:
                require_unlocked(self.root, state)
                self.book.update(last_revision=None, parking_lease=None)
                if resume and self.book['world_session'] != state.get('world_session'):
                    self.book['world_session'] = None
                # An explicit resume supersedes the pause/stop already present
                # when it started. A later control still reaches gate normally.
                if (prior_control and isinstance(prior_control.get('id'), str)
                        and prior_control.get('action') in ('pause', 'stop')):
                    self.book['last_control'] = prior_control['id']
            if not resume and not audit_only:
                self.book.update(campaign=self.book.get('campaign', 0) + 1, cursor=0)
            if directed is not None:
                self.book['work_selection'] = {**directed, 'campaign': self.book.get('campaign')}
            if prefix is not None:
                self.book['audit_resume_prefix'] = prefix
            self.gate(state)
            self.book.update(world_session=state['world_session'], phase='running', coverage_complete=False,
                             goal_complete=False, reason=None)
            self.save()
            try:
                if not audit_only:
                    while self.book['cursor'] < len(self.profile['regions']):
                        index = self.book['cursor']
                        region = self.profile['regions'][index]
                        if directed is not None and index not in directed['selected_indices']:
                            current = self.observer()
                            self.gate(current)
                            self.book.setdefault('work_skips', []).append({
                                'campaign': self.book.get('campaign'), 'region_index': index,
                                'baseline_sha256': directed['baseline_sha256'],
                                'baseline_unprotected_dark_floor': directed['baseline_dark_counts'][index],
                                'reason': 'complete_retained_baseline_has_no_unprotected_dark_floor',
                                'new_scan_performed': False, 'region_completed': False,
                                'placed_verified': 0, 'placement_credit': 0})
                            self.book['cursor'] += 1  # Queue position only; the full audit remains required.
                            self.save()
                            continue
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
                if prefix is None:
                    self.book['audits'] = []
                first_audit = prefix['prefix_count'] if prefix is not None else 0
                for index in range(first_audit,len(self.profile['regions'])):
                    region = self.profile['regions'][index]
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

    def arrival_height_plan(self,column,state,center,*,audit):
        """Audit from proved high air; only placement batches approach ground."""
        solid_top=max((row['pos'][1]+1 for row in column['blocks']
                       if row.get('fluid')or not row.get('passable',False)),default=None)
        if solid_top is None or solid_top+24>315:
            raise RegionsPaused('No bounded current column for safe parking')
        pos=state.get('pos')
        if (not isinstance(pos,list)or len(pos)!=3
            or any(type(v)not in(int,float)or not math.isfinite(v)for v in pos)):
            raise RegionsPaused('Current arrival height is unverified')
        park=[center[0],max(pos[1],solid_top+24)if audit else solid_top+24,center[2]]
        arrival=list(park)if audit else [center[0],solid_top+1.5,center[2]]
        if audit:
            movement=self.owner.profile['movement_bounds']
            low=[math.floor(arrival[0]-.35),math.floor(arrival[1]),math.floor(arrival[2]-.35)]
            high=[math.floor(arrival[0]+.35),math.floor(arrival[1]+1.8),math.floor(arrival[2]+.35)]
            if (any(low[i]<movement['min'][i]or high[i]>movement['max'][i]for i in range(3))
                or high[1]>319):
                raise RegionsPaused('Audit high parking body exceeds authorized loaded bounds')
            if any(all(low[i]<=row['pos'][i]<=high[i]for i in range(3))for row in column['blocks']):
                raise RegionsPaused('Audit high parking body column has an unsafe ceiling or obstruction')
        return {'actual_column':column,'arrival':arrival,'safe_park':park,
                'mode':'audit_high_guarded_arrival'if audit else 'lighting_low_arrival',
                'actual_current_height':pos[1],'solid_top':solid_top}

    def high_work_preflight(self, runner, low, high, directory):
        """One complete high scan may avoid descent; uncertain reads never do."""
        from lighting_batch_plan import plan
        from lighting_cli import validate_native_details
        from lighting_work_baseline import identity
        owner, client = self.owner, runner.c

        def fresh(expected=None):
            state = client.status(); owner.gate(state, client)
            key = identity(state)
            if (not isinstance(key.get('player_uuid'), str) or not key['player_uuid']
                    or not isinstance(key.get('projection_selection'), dict) or not key['projection_selection'].get('key')
                    or state.get('guard_busy') is not False or state.get('health') != 20
                    or state.get('recent_hurt_at', 0) > runner.hurt
                    or expected is not None and key != expected):
                raise RegionsPaused('High work preflight identity, guard or health is unverified')
            return state, key

        def scan(minimum, maximum, name, key):
            reply = client.request('scan', min=list(minimum), max=list(maximum), details=True)
            write_json(directory/name, reply)  # Even a terminal partial/unloaded reply is retained.
            volume = math.prod(b-a+1 for a,b in zip(minimum,maximum))
            if (reply.get('phase') != 'done' or identity(reply) != key
                    or not isinstance(reply.get('id'), str) or reply['id'] != client.last
                    or any(type(reply.get(k)) is not int for k in ('control_revision','scan_start_revision',
                               'scan_end_revision','scan_cells_read','scan_total_cells','scan_started_at','scan_ended_at'))
                    or any(reply[k] != client.rev for k in ('control_revision','scan_start_revision','scan_end_revision'))
                    or reply['scan_cells_read'] != volume or reply['scan_total_cells'] != volume
                    or not 0 < reply['scan_started_at'] <= reply['scan_ended_at']):
                raise RegionsPaused('High preflight lacks the exact complete current native scan')
            return reply, validate_native_details(scan_cells(reply, minimum, maximum, client.world))

        before, key = fresh()
        pos = before['pos']
        column_low = [math.floor(pos[0]-.35), -64, math.floor(pos[2]-.35)]
        column_high = [math.floor(pos[0]+.35), 319, math.floor(pos[2]+.35)]
        owner.book['pending'].update(stage='high_preflight_column'); owner.save()
        column, _ = scan(column_low, column_high, 'high-preflight-body-column.json', key)
        current, _ = fresh(key)
        if any(abs(current['pos'][i]-pos[i]) > .05 for i in range(3)):
            raise RegionsPaused('High preflight actual column pose changed')
        ground = max((v['pos'][1]+1 for v in column['blocks']
                      if v.get('fluid') or not v.get('passable', False)), default=None)
        if ground is None or current['pos'][1]-ground < 20:
            raise RegionsPaused('High preflight has no actual guarded ground clearance')
        anchor = [current['pos'][0], max(current['pos'][1]+.35, ground+24.35), current['pos'][2]]
        body_low = [math.floor(anchor[0]-.35), math.floor(current['pos'][1]), math.floor(anchor[2]-.35)]
        body_high = [math.floor(anchor[0]+.35), math.floor(anchor[1]+1.8), math.floor(anchor[2]+.35)]
        movement = owner.profile['movement_bounds']
        if (any(body_low[i]<movement['min'][i] or body_high[i]>movement['max'][i] for i in range(3))
                or body_high[1]>319 or any(all(body_low[i]<=v['pos'][i]<=body_high[i] for i in range(3))
                                         for v in column['blocks'])):
            raise RegionsPaused('High preflight canonical anchor has an unsafe body column')
        owner.book['pending'].update(stage='high_preflight_anchor'); owner.save()
        native = client.checked('material_job_park', park_target=anchor)
        write_json(directory/'high-preflight-native-anchor.json', native)
        lease = native.get('supervision_lease') or {}
        if (native.get('phase') != 'done' or native.get('world_session') != client.world
                or lease.get('kind') != 'materials' or lease.get('id') != client.heartbeat.id
                or lease.get('job_session') != client.task or lease.get('world_session') != client.world
                or lease.get('revision') != client.rev or lease.get('remote_finish') != 'guard'
                or lease.get('park_target') != anchor):
            raise RegionsPaused('High preflight native parking anchor is unconfirmed')
        client.park_target = list(anchor)  # Adopt only this exact native setter receipt; it starts no movement.
        owner.book['pending'].update(stage='high_preflight_scan'); owner.save()
        reply, cells = scan(low, high, 'high-preflight-region.json', key)
        observed, _ = fresh(key)
        if (stock(observed) != stock(before)
                or any(not column_low[i] <= math.floor(observed['pos'][i]-.3)
                       or math.floor(observed['pos'][i]+.3) > column_high[i] for i in (0,2))
                or not client.park_near(observed)):
            raise RegionsPaused('High preflight pose or torch inventory changed')
        targets = plan(cells, low, high, observed['pos'], owner.profile['protected'],
                       limit=min(owner.profile['batch_torches'], stock(observed)))
        counts = risk_counts(cells, owner.profile['protected'])
        proof = {'scope':'single_high_preflight_scan', 'world_session':client.world,
                 'task_session':client.task, 'request_id':reply['id'], 'observed_at':reply['scan_ended_at'],
                 'counts':counts, 'predicted_targets':targets, 'placement_credit':0,
                 'descent_performed':False, 'interaction_performed':False, 'goal_complete':False}
        write_json(directory/'high-preflight-plan.json', proof)
        runner.report['high_work_preflight'] = proof
        if not targets:
            runner.report.update(state='no_targets_after_single_high_preflight_scan',
                remaining_risk=counts['zombie_block_light_risk'],
                remaining_unprotected_risk=counts['unprotected_dark_floor'])
            runner.report['progress'].update(eligible_candidates=0,
                dark_floor_last_observed=counts['zombie_block_light_risk'],
                dark_floor_observation_stage='single_high_preflight_scan')
            runner.save()
        return {'placed_verified':0, 'eligible_remaining':len(targets),
                'unprotected_dark_floor':counts['unprotected_dark_floor'],
                'observed_at':reply['scan_ended_at'], 'work_scan_scope':'single_high_preflight_scan'}

    def current_loaded_park(self, survey, state, directory):
        """Prove this loaded body column before acquiring a distant-route lease."""
        self.owner.gate(state)
        pos=state['pos']
        low=[math.floor(pos[0]-.35),-64,math.floor(pos[2]-.35)]
        high=[math.floor(pos[0]+.35),319,math.floor(pos[2]+.35)]
        column=survey.request('scan',min=low,max=high,details=True)
        scan_cells(column,low,high,survey.world)
        write_json(directory/'current-park-column.json',column)
        ground=max((row['pos'][1]+1 for row in column['blocks']
                    if row.get('fluid') or not row.get('passable',False)),default=None)
        fresh=survey.status();self.owner.gate(fresh)
        if (fresh.get('world_session')!=state.get('world_session')
                or any(abs(fresh['pos'][i]-pos[i])>.05 for i in range(3))
                or ground is None or fresh['pos'][1]-ground<20):
            raise RegionsPaused('Current loaded body column does not prove twenty-block guarded parking clearance')
        park=list(fresh['pos'])
        write_json(directory/'current-park-plan.json',{'park_target':park,'ground_top':ground,
                                                      'world_session':survey.world,'observed':fresh})
        return park

    def preload_region(self, client, target, directory):
        """Approach on short inspected legs; never scan a distant full corridor."""
        from material_jobs.acquisition import _travel
        owner=self.owner;trace=[];guard_budget={}
        path=directory/'preload-route.json'
        for index in range(64):
            state=client.status();owner.gate(state,client)
            here=list(state['pos'])
            if math.hypot(target[0]-here[0],target[2]-here[2])<=16:
                write_json(path,{'world_session':client.world,'task_session':client.task,
                                 'target':target,'arrived_near':True,'legs':trace})
                return
            axis=0 if abs(target[0]-here[0])>=abs(target[2]-here[2]) else 2
            point=list(here);delta=target[axis]-here[axis]
            point[axis]+=max(-32,min(32,delta))
            movement=owner.profile['movement_bounds']
            low=[math.floor(min(here[i],point[i])-(.35 if i!=1 else 0)) for i in range(3)]
            high=[math.floor(max(here[i],point[i])+(.35 if i!=1 else 1.8)) for i in range(3)]
            if any(low[i]<movement['min'][i] or high[i]>movement['max'][i] for i in range(3)):
                raise RegionsPaused('Preload travel would leave the authorized movement box')
            leg={'sequence':index+1,'from':here,'target':point,'state':'pending','route':[]}
            trace.append(leg)
            owner.book['pending'].update(stage='travel',travel_stage='preload',preload_leg=index+1)
            owner.save()
            write_json(path,{'world_session':client.world,'task_session':client.task,
                             'target':target,'arrived_near':False,'legs':trace})
            try:
                _travel(client,point,lambda:owner.gate(client.status(),client),leg['route'],guard_budget,
                        clearance_padding=2.32,obstacle_margin=5.1,keep_cruise=True)
                actual=client.status();owner.gate(actual,client)
                if (math.hypot(actual['pos'][0]-point[0],actual['pos'][2]-point[2])>.55
                        or actual['pos'][1]<point[1]-.55):
                    raise RegionsPaused('Original short preload leg arrival is unconfirmed')
                leg.update(state='done',actual=actual['pos'],request_id=client.last)
            finally:
                write_json(path,{'world_session':client.world,'task_session':client.task,
                                 'target':target,'arrived_near':False,'legs':trace})
        raise RegionsPaused('Bounded preload leg budget exhausted; original region remains pending')

    def __call__(self, region, directory, *, audit):
        from material_client import MaterialClient
        from material_jobs.acquisition import _travel
        owner = self.owner

        class RegionClient(MaterialClient):
            def request(self, op, **params):
                if op == 'navigate' and not owner.cleaning:
                    movement = owner.profile['movement_bounds']
                    start, target = self.status()['pos'], params['target']
                    if (owner.book.get('pending',{}).get('travel_stage')=='preload'
                            and math.dist(start,target)>32.000001):
                        raise RegionsPaused('Preload native navigation exceeds the thirty-two-block leg bound')
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
        high_preflight = False
        try:
            owner.opening = True
            from material_client import Client
            survey=Client(owner.root,directory/'opening-survey',server=owner.profile['server'])
            distant=math.hypot(park[0]-state['pos'][0],park[2]-state['pos'][2])>32
            if distant:
                current_park=self.current_loaded_park(survey,state,directory)
                client=RegionClient(owner.root,directory,server=owner.profile['server'],remote_finish='guard',
                                    park_target=current_park,record_experience=False)
                owner.opening=False
                owner.book['pending'].update(stage='travel',travel_stage='preload',world_session=client.world,
                                             task_session=client.task,lease=client.heartbeat.id)
                owner.save()
                self.preload_region(client,park,directory)
                owner.book['pending'].update(stage='arrival_survey',travel_stage='preloaded')
                owner.save()
            px,pz=math.floor(park[0]),math.floor(park[2])
            column_low=[math.floor(park[0]-.35),-64,math.floor(park[2]-.35)]
            column_high=[math.floor(park[0]+.35),319,math.floor(park[2]+.35)]
            column=(client or survey).request('scan',min=column_low,max=column_high,details=True)
            scan_cells(column,column_low,column_high,(client or survey).world)
            actual=(client or survey).status();owner.gate(actual,client)
            height_plan=self.arrival_height_plan(column,actual,park,audit=True)
            if not audit: height_plan['mode']='lighting_high_preflight_arrival'
            park,arrival=height_plan['safe_park'],height_plan['arrival']
            write_json(directory/'arrival-height-plan.json',height_plan)
            if client is None:
                client = RegionClient(owner.root, directory, server=owner.profile['server'], remote_finish='guard',
                                      park_target=park, record_experience=False)
            else:
                client.park_target=park
            owner.opening = False
            owner.book['pending'].update(stage='travel', world_session=client.world,
                                         task_session=client.task, lease=client.heartbeat.id,travel_stage='arrival')
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
                high_preflight = True
                result = self.high_work_preflight(runner,low,high,directory)
                if result['eligible_remaining']:
                    high_preflight = False
                    # A high prediction is not placement clearance; retain the original low work checks.
                    current=client.status();owner.gate(current,client)
                    work_plan=self.arrival_height_plan(column,current,park,audit=False)
                    # Keep the canonical native high anchor during descent/unknown travel.
                    # Normal completed work later recomputes and confirms its own park.
                    work_plan['safe_park']=list(client.park_target)
                    work_plan['park_anchor_source']='confirmed_high_preflight_native_anchor'
                    write_json(directory/'low-work-arrival-height-plan.json',work_plan)
                    owner.book['pending'].update(stage='travel',travel_stage='arrival');owner.save()
                    low_trace=[]
                    _travel(client,work_plan['arrival'],lambda:owner.gate(client.status(),client),low_trace,
                            clearance_padding=2.32,obstacle_margin=5.1)
                    write_json(directory/'low-work-arrival-route.json',low_trace)
                    owner.book['pending']['stage']='lighting';owner.save()
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
                if runner is not None and not park_started and not high_preflight:
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
    selected=result.get('work_selection')or{}
    directed=selected.get('campaign')==result.get('campaign') and bool(selected)
    return {k:v for k,v in {'phase':result.get('phase'),'reason':result.get('reason',result.get('detail','')),
        'cursor':cursor,'total_regions':total,'placed_verified':sum(r.get('placed_verified',0) for r in batches),
        'coverage_complete':result.get('coverage_complete',False),'pending_stage':(result.get('pending')or{}).get('stage'),
        'worker_running':result.get('worker_running'),'journal':result.get('journal'),'ai_calls':result.get('ai_calls',0),
        'directed_work_regions':len(selected['selected_indices']) if directed else None,
        'work_skipped_without_scan':sum(row.get('campaign')==result.get('campaign')
                                       for row in result.get('work_skips',[])) if directed else None,
        'final_audit_regions':total if directed else None}.items() if v is not None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, default=Path('/Applications/.minecraft/versions/26.1.2'))
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--network-evidence',type=Path)
    parser.add_argument('--travel-evidence',type=Path,help='Retained manifest for a known terminal AirOnly stop and separately proved same-owner recovery')
    parser.add_argument('--audit-prefix',type=Path,help='Retained current complete contiguous audit prefix; continue the remaining registered regions')
    parser.add_argument('--work-baseline',type=Path,
                        help='Only work retained-baseline dark regions; resume preserves this campaign; final audit still visits all regions')
    parser.add_argument('--verbose',action='store_true',help='Print full original journal; default emits a compact status')
    parser.add_argument('action', choices=('run', 'resume', 'audit', 'status', 'pause', 'stop', 'reconcile-travel', 'reconcile-known-travel', 'reconcile-entity', 'reconcile-guard', 'reconcile-own-torch', 'reconcile-opening', 'reconcile-network-travel'))
    parser.add_argument('--auto-supply',action='store_true',help='缺火把时调用原生材料任务，验证后继续')
    parser.add_argument('--torch-target',type=int,default=128)
    parser.add_argument('--max-supplies',type=int,default=32)
    args = parser.parse_args(argv)
    try:
        if args.work_baseline is not None and args.action not in ('run', 'resume'):
            raise ValueError('A directed work baseline is only available for run/resume')
        if args.travel_evidence is not None and args.action!='reconcile-known-travel':
            raise ValueError('Known-travel evidence is only available for explicit read-only reconciliation')
        if args.audit_prefix is not None and (args.action not in ('resume','audit')or args.auto_supply):
            raise ValueError('An audit prefix requires explicit resume/audit without automatic supply')
        worker = RegionsWorker(args.game_dir / 'config/twob2tkit/automation', _read(args.profile), args.out,
                               work_baseline=args.work_baseline,audit_prefix=args.audit_prefix)
        if args.auto_supply:
            if args.action!='resume':raise ValueError('Automatic supply is only available for resume')
            from lighting_supply_workflow import LightingSupplyWorkflow
            workflow=LightingSupplyWorkflow(lambda:RegionsWorker(args.game_dir/'config/twob2tkit/automation',_read(args.profile),args.out,
                                                                 work_baseline=args.work_baseline),
                                            target=args.torch_target,max_supplies=args.max_supplies)
            value=workflow.run(); result=compact(value.get('lighting_result') or worker.status())
            result.update(workflow_phase=value['phase'],supplies_completed=len(value['supplies']),pending_supply=bool(value.get('pending')))
            print(json.dumps(result,ensure_ascii=False));return 2 if value['phase']=='waiting' else 0
        from lighting_entity_reconcile import reconcile as reconcile_entity, GUARD_ERROR, OWN_TORCH_ERROR
        result = (worker.reconcile_known_travel(travel_evidence=args.travel_evidence) if args.action=='reconcile-known-travel' else worker.reconcile_network_travel(network_evidence=args.network_evidence) if args.action=='reconcile-network-travel' else worker.reconcile_opening() if args.action=='reconcile-opening' else reconcile_entity(worker,allowed_error=OWN_TORCH_ERROR) if args.action=='reconcile-own-torch' else reconcile_entity(worker,allowed_error=GUARD_ERROR) if args.action=='reconcile-guard' else reconcile_entity(worker) if args.action == 'reconcile-entity' else worker.reconcile_travel() if args.action == 'reconcile-travel' else worker.status() if args.action == 'status' else worker.command(args.action)
                  if args.action in ('pause', 'stop') else worker.run(resume=args.action == 'resume', audit_only=args.action == 'audit'))
        print(json.dumps(result if args.verbose else compact(result), ensure_ascii=False))
        return 0 if result.get('phase') not in ('waiting', 'waiting_materials', 'waiting_unresolved', 'audited_with_remaining_risk') else 2
    except (RuntimeError, ValueError, OSError, KeyError) as error:
        print(json.dumps({'phase': 'waiting', 'detail': str(error), 'ai_calls': 0}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
