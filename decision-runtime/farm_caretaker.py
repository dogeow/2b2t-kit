"""Persistent local farm cycles. No model, reconnect, unlock, or invented receipt.

A stage owns its original cycle directory. After an uncertain call only explicit
read-only reconciliation outside this coordinator can make that work reusable.
next_due/started_at use Unix seconds; native observations retain milliseconds.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from kit_runtime.journal import write_json
from material_jobs.protocol import JobPaused, server_key
from safety_interlock import require_unlocked

STAGES = ('harvest_store', 'breed', 'surplus', 'cook_store')
ACTIVE_FLAGS = ('borer_active', 'chopping', 'navigating', 'printing', 'planter_active',
                'feeder_active', 'fisher_active', 'native_material_busy')


class CaretakerPaused(JobPaused):
    pass


def _point(p, integer=False):
    return (isinstance(p, list) and len(p) == 3
            and all(type(n) is int if integer else type(n) in (int, float) and math.isfinite(n) for n in p)
            and abs(p[0]) <= 30_000_000 and abs(p[2]) <= 30_000_000 and -64 <= p[1] <= 319)


def validate_profile(value):
    p = deepcopy(value)
    if (not isinstance(p, dict) or p.get('schema') != 1 or p.get('authorized') is not True
            or not isinstance(p.get('server'), str) or not p['server'].strip()
            or p.get('dimension') != 'minecraft:overworld'):
        raise ValueError('An authorized server/Overworld caretaker profile is required')
    p['server'] = server_key(p['server'].strip())
    for key, default, low, high in (('interval_seconds', 300, 1, 86400), ('adult_keep', 20, 2, 64),
                                    ('potato_reserve', 4, 4, 4), ('cooked_food_reserve', 8, 8, 64)):
        p.setdefault(key, default)
        if type(p[key]) is not int or not low <= p[key] <= high:
            raise ValueError('Invalid caretaker policy: '+key)
    fields = p.setdefault('potato_fields', [])
    if not isinstance(fields, list) or len(fields) > 8:
        raise ValueError('At most eight explicitly registered fields are supported')
    from potato_farm import plan
    for field in fields:
        plan(field)
    region = p.get('livestock_region')
    types = p.setdefault('livestock_types', ['minecraft:cow', 'minecraft:sheep'] if region else [])
    if (not isinstance(types, list) or any(not isinstance(t,str) for t in types)
            or len(set(types)) != len(types) or any(t not in ('minecraft:cow', 'minecraft:sheep', 'minecraft:chicken') for t in types)):
        raise ValueError('Registered livestock must be cows, sheep or chickens')
    if types:
        if not isinstance(region,dict): raise ValueError('Livestock region must be an explicit block box')
        low, high = region.get('min'), region.get('max')
        if (not _point(low, True) or not _point(high, True)
                or any(a > b or b-a >= 32 for a,b in zip(low,high))
                or math.prod(b-a+1 for a,b in zip(low,high)) > 8192):
            raise ValueError('Livestock needs a bounded explicitly registered region')
    if not fields and not types:
        raise ValueError('Register at least one field or livestock region')
    depots = p.get('depots')
    if (not isinstance(depots, list) or not 1 <= len(depots) <= 16
            or any(not _point(pos, True) for pos in depots)
            or len({tuple(pos) for pos in depots}) != len(depots)
            or not _point(p.get('park_target'))):
        raise ValueError('Explicit destination depots and a guarded park target are required')
    # This worker is local. Do not turn a registered farm into long-distance travel.
    points = [f['center'] for f in fields]+depots+[p['park_target']]
    if types:
        points += [region['min'], region['max']]
    anchor = p['park_target']
    if any(math.hypot(pos[0]-anchor[0], pos[2]-anchor[2]) > 32 for pos in points):
        raise ValueError('Every registered worksite must be within 32 horizontal blocks of parking')
    return p


def _read(path):
    return json.loads(Path(path).read_text())


def _counts(state):
    from material_plan import inventory_counts
    return dict(inventory_counts(state))


class Caretaker:
    def __init__(self, automation, profile, out=None, *, observer=None, adapter_factory=None, clock=time.time):
        self.root, self.profile, self.clock = Path(automation), validate_profile(profile), clock
        scope = self.profile['server']+'|'+self.profile['dimension']
        self.key = hashlib.sha256(scope.encode()).hexdigest()[:20]
        home = self.root/'farm-caretakers'/self.key
        home.mkdir(parents=True, exist_ok=True)
        with (home/'registry.lock').open('a+') as registration_lock:
            fcntl.flock(registration_lock,fcntl.LOCK_EX)
            registry = home/'registry.json'
            directory = Path(out).resolve() if out is not None else (home/'journal').resolve()
            if registry.exists():
                saved = _read(registry)
                if saved.get('profile') != self.profile:
                    raise ValueError('This server/dimension already has a different caretaker profile')
                registered = Path(saved['directory'])
                if out is not None and directory != registered:
                    raise ValueError('Changing output cannot bypass the registered caretaker journal')
                directory = registered
            else:
                write_json(registry, {'profile': self.profile, 'directory': str(directory)})
            self.out = directory; self.out.mkdir(parents=True, exist_ok=True)
            self.path, self.control = self.out/'caretaker.json', self.out/'control.json'
            self.lock_path = home/'worker.lock'
            existing = self.path.exists()
            self.book = _read(self.path) if existing else {
                'schema': 1, 'profile': self.profile, 'enabled': False, 'paused': False,
                'reason': 'NOT_STARTED', 'next_due': 0, 'cycle': 0, 'stage': STAGES[0],
                'pending': None, 'current_cycle': None, 'world_session': None,
                'last_revision': None, 'last_control': None, 'ai_calls': 0}
            if (not isinstance(self.book, dict) or self.book.get('profile') != self.profile
                    or self.book.get('schema') != 1 or type(self.book.get('enabled')) is not bool
                    or type(self.book.get('paused')) is not bool or self.book.get('stage') not in STAGES
                    or type(self.book.get('cycle')) is not int or self.book['cycle'] < 0
                    or type(self.book.get('next_due')) not in (int,float) or not math.isfinite(self.book['next_due'])
                    or self.book.get('ai_calls') != 0):
                raise ValueError('Caretaker journal is malformed; no control will be acquired')
            self.observer = observer or self._observe
            self.adapter_factory = adapter_factory or NativeStages
            self.adapter = None
            self._opening = False
            self._idle_since = None
            if not existing: self.save()

    def _observe(self):
        from live_snapshot import read_fresh
        return read_fresh(self.root)

    def save(self):
        write_json(self.path, self.book)

    def status(self):
        return deepcopy(self.book)

    @contextmanager
    def worker_lock(self):
        with self.lock_path.open('a+') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error: raise RuntimeError('Another local caretaker worker is running') from error
            try: yield
            finally: fcntl.flock(lock, fcntl.LOCK_UN)

    def command(self, action):
        if action not in ('pause', 'stop', 'resume'):
            raise ValueError('Caretaker control must be pause, stop or resume')
        request = {'id': uuid.uuid4().hex, 'action': action, 'key': self.key}
        write_json(self.control, request)
        return request

    def _halt(self, reason, *, disabled=False):
        self.book.update(paused=True, reason=reason)
        if disabled: self.book['enabled'] = False
        self.save()
        raise CaretakerPaused(reason)

    def _client(self):
        return getattr(self.adapter, 'client', None) if self.adapter is not None else None

    def _hard_gate(self, state, *, rebinding=False, explicit=False):
        try: require_unlocked(self.root, state)
        except (RuntimeError, OSError, ValueError): self._halt('SAFETY_HOLD', disabled=True)
        if state.get('connected') is not True:
            self._halt('DISCONNECTED' if state.get('connected') is False else 'WORLD_UNAVAILABLE', disabled=True)
        if (server_key(state.get('server')) != self.profile['server']
                or state.get('dimension') != self.profile['dimension']):
            self._halt('WORLD_SCOPE_CHANGED', disabled=True)
        if (self.book['world_session'] is not None
                and state.get('world_session') != self.book['world_session'] and not rebinding):
            self._halt('WORLD_SESSION_CHANGED', disabled=True)
        if not isinstance(state.get('world_session'), str) or not state['world_session']:
            self._halt('WORLD_UNAVAILABLE', disabled=True)
        if type(state.get('health')) not in (int, float) or not math.isfinite(state['health']):
            self._halt('HEALTH_UNAVAILABLE', disabled=True)
        if state['health'] != 20:
            self._halt('HEALTH_NOT_READY', disabled=True)
        if (type(state.get('food')) is not int or not 0 <= state['food'] <= 20
                or type(state.get('under_water')) is not bool):
            self._halt('SURVIVAL_UNAVAILABLE', disabled=True)
        if type(state.get('control_revision')) is not int or state['control_revision'] < 0:
            self._halt('CONTROL_UNAVAILABLE', disabled=True)
        if state.get('food', 0) < 8 or state.get('under_water') is not False:
            self._halt('WAIT_FOOD_OR_DRY_STAND')
        stop = state.get('control_stop') or {}
        if not isinstance(stop, dict): self._halt('WAIT_STOP_WITNESS', disabled=True)
        acknowledged=self.book.get('acknowledged_stop')=={'world_session':state.get('world_session'),'revision':state.get('control_revision')}
        if stop.get('kind') == 'emergency' and stop.get('revision') == state.get('control_revision') and not explicit and not acknowledged:
            self._halt('EMERGENCY_STOP', disabled=True)
    def _gate(self, state, *, idle=False, rebinding=False, explicit=False):
        self._hard_gate(state, rebinding=rebinding,explicit=explicit)
        stop=state.get('control_stop') or {}
        if state.get('manual_movement') is True:
            self._idle_since = None
            # Revision changes are auto-adopted only with a structured native witness.
            if stop.get('kind') == 'manual' and stop.get('revision') == state.get('control_revision'):
                self.book['last_revision'] = state['control_revision']
                self.book['manual_stop'] = {'world_session':state['world_session'], 'revision':state['control_revision']}
            else:
                self._halt('WAIT_STOP_WITNESS', disabled=True)
            self._halt('MANUAL_INPUT')
        if state.get('manual_movement') is not False:
            self._halt('CONTROL_UNAVAILABLE', disabled=True)
        client = self._client()
        if (not explicit and not rebinding and not self._opening and client is None and self.book.get('last_revision') is not None
                and state.get('control_revision') != self.book['last_revision']):
            self._halt('CONTROL_CHANGED', disabled=True)
        lease = state.get('supervision_lease') or {}
        if not self._opening:
            if client is not None:
                from material_jobs_backend import owns_material_state
                if not owns_material_state(client, state): self._halt('CONTROL_CHANGED', disabled=True)
            elif lease and not (lease.get('kind') == 'parking' and lease.get('id') == self.book.get('parking_lease')):
                self._halt('WAIT_OTHER_LEASE')
        if idle:
            if state.get('food',0)<18: self._halt('WAIT_FOOD_OR_DRY_STAND')
            if state.get('screen') or any(state.get(k) for k in ACTIVE_FLAGS) or state.get('build_job',{}).get('active'):
                self._halt('WAIT_PLAYER_OR_OTHER_JOB')
            pos = state.get('pos')
            if not _point(pos) or math.hypot(pos[0]-self.profile['park_target'][0], pos[2]-self.profile['park_target'][2]) > 32:
                self._halt('WAIT_LOCAL_WORKSITE')

    def resume(self):
        if self.book.get('pending'):
            raise CaretakerPaused('WAIT_RECONCILE: original pending cycle cannot be replayed')
        state = self.observer()
        # No implicit adoption of partial work after a reconnect.
        rebind = self.book.get('current_cycle') is None
        lease = state.get('supervision_lease') or {}
        previous = self.book.get('parking_lease')
        if lease.get('kind') == 'parking' and state.get('guard_armed') is True and state.get('guard_pve_only') is True:
            self.book['parking_lease'] = lease.get('id')
        try: self._gate(state, idle=True, rebinding=rebind,explicit=True)
        except CaretakerPaused:
            self.book['parking_lease'] = previous; self.save(); raise
        self.book.update(enabled=True, paused=False, reason='', world_session=state['world_session'],
                         last_revision=state['control_revision'],
                         acknowledged_stop={'world_session':state['world_session'],'revision':state['control_revision']})
        self._idle_since = None
        self.save()
        return self.status()

    def _consume_control(self):
        if not self.control.exists(): return
        request = _read(self.control)
        if (not isinstance(request, dict) or request.get('key') != self.key
                or request.get('action') not in ('pause','stop','resume') or not isinstance(request.get('id'),str)):
            self._halt('INVALID_CONTROL', disabled=True)
        if request['id'] == self.book.get('last_control'): return
        self.book['last_control'] = request['id']
        if request['action'] == 'resume':
            try: self.resume()
            except CaretakerPaused as error:
                self.book['resume_wait'] = str(error)
                if not self.book.get('reason'): self.book['reason'] = str(error)
                self.save()
        else:
            self.book.update(paused=True, reason='USER_'+request['action'].upper())
            if request['action'] == 'stop': self.book['enabled'] = False
            self.save()

    def checkpoint(self):
        self._consume_control()
        if not self.book['enabled'] or self.book['paused']:
            raise CaretakerPaused(self.book['reason'])
        self._gate(self.observer())

    def _close(self, normal):
        if self.adapter is None: return
        adapter = self.adapter
        def cleanup_wait(code, detail=''):
            self.book.update(paused=True, cleanup_wait={'code':code, 'detail':detail})
            if not self.book.get('reason'): self.book['reason'] = code
            if normal and self.book.get('pending') is None:
                self.book['pending'] = {'stage':'parking', 'directory':self.book['current_cycle']['directory']}
        try:
            result = adapter.close(normal=normal)
            if normal:
                if (not isinstance(result,dict) or result.get('parked') is not True
                        or not isinstance(result.get('parking_lease'),str)
                        or type(result.get('revision')) is not int or result['revision']<0):
                    cleanup_wait('WAIT_PARK_RECEIPT')
                else:
                    self.book.update(parking_lease=result['parking_lease'], last_revision=result['revision'])
        except Exception as error:
            cleanup_wait('WAIT_FINISH', str(error))
        finally:
            self.adapter = None; self.save()

    def _cycle(self, state):
        if self.book['current_cycle'] is not None: return
        self.book['cycle'] += 1
        directory = self.out/('cycle-%06d' % self.book['cycle']); directory.mkdir(exist_ok=True)
        self.book.update(stage=STAGES[0], current_cycle={'id':self.book['cycle'], 'directory':str(directory),
                         'world_session':state['world_session'], 'started_at':self.clock(),
                         'baseline':_counts(state), 'receipts':{}})
        self.save()

    def tick(self):
        try:
            self._consume_control()
            if not self.book['enabled']:
                self._close(False);return self.status()
            state = self.observer()
            self._hard_gate(state)
            if self.book['pending']:
                self._close(False)
                self.book['paused'] = True
                if not self.book.get('reason'): self.book['reason'] = 'WAIT_RECONCILE'
                self.save(); return self.status()
            if self.book['paused']:
                # Only observed manual input may auto-yield back after 3 idle seconds.
                if self.book['reason'] != 'MANUAL_INPUT':
                    self._close(False);return self.status()
                self._gate(state, idle=True)
                stop = state.get('control_stop') or {}
                if (stop.get('kind') != 'manual' or stop.get('revision') != state['control_revision']
                        or self.book.get('manual_stop') != {'world_session':state['world_session'], 'revision':state['control_revision']}):
                    self._halt('WAIT_STOP_WITNESS', disabled=True)
                if self._idle_since is None: self._idle_since = self.clock()
                if self.clock()-self._idle_since < 3: return self.status()
                self.book.update(paused=False, reason=''); self.save()
            self._gate(state, idle=self.adapter is None)
            if self.clock() < self.book['next_due']: return self.status()
            self._cycle(state)
            cycle = self.book['current_cycle']; stage = self.book['stage']
            out = Path(cycle['directory'])/stage; out.mkdir(exist_ok=True)
            # Durable intent precedes client acquisition and all stage calls.
            self.book['pending'] = {'stage':stage, 'directory':str(out)}; self.save()
            if self.adapter is None:
                self._opening = True
                try:
                    self.adapter = self.adapter_factory(self.root, self.profile, cycle, self.checkpoint, state)
                finally: self._opening = False
            reply = self.adapter.run(stage, self.profile, deepcopy(cycle), out, self.checkpoint)
            # A primitive may catch an exception internally. A persisted stop
            # still wins over any reply and retains the original uncertain intent.
            self.checkpoint()
            if (not isinstance(reply,dict) or reply.get('pending') is not False
                    or not isinstance(reply.get('receipts'),list)):
                self.book.update(paused=True, reason='WAIT_RECONCILE'); self.save()
                self._close(False); return self.status()
            self.book['pending'] = None
            cycle['receipts'][stage] = deepcopy(reply)
            if reply.get('phase') not in ('done','idle'):
                self.book.update(paused=True, reason=reply.get('code') or 'WAIT_STAGE'); self.save()
                self._close(True); return self.status()
            index = STAGES.index(stage)+1
            if index < len(STAGES):
                self.book['stage'] = STAGES[index]; self.save()
            else:
                self._close(True)
                if self.book['pending'] or self.book['paused']: return self.status()
                write_json(Path(cycle['directory'])/'receipt.json', cycle)
                self.book.update(current_cycle=None, stage=STAGES[0], next_due=self.clock()+self.profile['interval_seconds'])
                self.save()
        except CaretakerPaused:
            self._close(False)
        except Exception as error:
            self.book.update(paused=True, reason='WAIT_RECONCILE: '+str(error)); self.save(); self._close(False)
        return self.status()

    def worker_running(self):
        with self.lock_path.open('a+') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: return True
            fcntl.flock(lock,fcntl.LOCK_UN);return False

    def run(self, *, resume=False, poll_seconds=1, sleep=time.sleep):
        if not 0 < poll_seconds <= 10: raise ValueError('Polling must be 0..10 seconds')
        with self.worker_lock():
            self.book=_read(self.path)
            if resume or not self.book['enabled']: self.resume()
            try:
                while self.book['enabled'] or self.book.get('reason') == 'USER_PAUSE':
                    self.tick()
                    if not self.book['enabled']: break
                    sleep(poll_seconds)
            except BaseException:
                self.book.update(enabled=False,paused=True,reason='WORKER_INTERRUPTED');self.save();raise
            finally: self._close(False)
        return self.status()


class NativeStages:
    """One existing Backend/JobClient for this cycle; stage primitives live elsewhere."""
    def __init__(self, root, profile, cycle, checkpoint, state):
        from material_jobs.protocol import validate_request
        from material_jobs_backend import create_backend
        from farm_caretaker_stages import create_stages
        self.backend = self.client = None
        request = validate_request({'schema':1, 'id':'farm-cycle-'+str(cycle['id']), 'mode':'item',
            'targets':{'minecraft:baked_potato':profile['cooked_food_reserve']},
            'created_at':max(1,state['time']), 'context':{k:state[k] for k in ('server','dimension','world_session')} |
            {'expected_revision':state['control_revision'], 'start_pos':state['pos']}})
        backend_out=Path(cycle['directory'])/'backend';backend_out.mkdir(parents=True,exist_ok=True)
        self.backend = create_backend(request, root, backend_out, checkpoint)
        if any(pos not in self.backend.profile.get('depots',[]) for pos in profile['depots']):
            raise ValueError('Caretaker destination is not an approved material depot')
        self.backend.profile['park_target'] = profile['park_target'][:]
        self.backend.out.mkdir(parents=True,exist_ok=True)
        try:
            self.client = self.backend.ensure_client()
            if self.backend.client is not self.client: raise RuntimeError('Caretaker must use its existing Backend client')
            self.stages = create_stages(self.client,self.backend)
            if not isinstance(self.stages,dict) or set(self.stages) != set(STAGES):
                raise ValueError('Caretaker stage capabilities are incomplete')
        except BaseException:
            self.client=self.backend.client or self.client
            try: self.close(normal=False)
            except Exception: pass  # Original intent remains uncertain; heartbeat cleanup is in close().
            raise

    def run(self, stage, profile, cycle, out, checkpoint):
        return self.stages[stage](profile,cycle,out,checkpoint)

    def close(self, *, normal):
        if self.client is None: return {'parked':False}
        c = self.client
        if normal:
            try: self.backend.finish()
            finally:
                c.heartbeat.close()
                if c.job_progress: c.job_progress.close()
            proof = _read(c.out/'stock-safety.json')
            from live_snapshot import read_fresh
            state = read_fresh(c.root); lease = state.get('supervision_lease') or {}
            return {'parked':proof.get('action')=='KEEP_PVE_GUARD' and proof.get('lease')==c.heartbeat.id
                    and state.get('connected') is True and state.get('world_session')==c.world
                    and state.get('health')==20 and state.get('guard_armed') is True
                    and state.get('guard_pve_only') is True and state.get('flight') is True
                    and lease.get('kind')=='parking' and lease.get('id')==c.heartbeat.id,
                    'parking_lease':c.heartbeat.id, 'revision':state.get('control_revision')}
        try:
            from live_snapshot import read_fresh
            from material_jobs_backend import owns_material_state
            state = read_fresh(c.root)
            if owns_material_state(c,state) and state.get('health',0)>=14 and not state.get('safety_hold',{}).get('active'):
                self.backend.cleaning = True
                c.request('material_job_pause',release=False)
        finally:
            c.heartbeat.close()
            if c.job_progress: c.job_progress.close()
            self.backend.cleaning = False
        return {'parked':False}
