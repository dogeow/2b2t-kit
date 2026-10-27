"""Pure evidence for repeated, unresolved injury while an owned worker is idle."""
import math

ENVIRONMENTAL_ATTACKERS = frozenset(('火', '岩浆', '岩浆块', '仙人掌', '甜浆果丛',
                                   '溺水', '冰冻', '窒息', '干涸'))

class StuckDamageWitness:
    def __init__(self, world, task, lease_id):
        self.scope = world, task, lease_id
        self.triggered = False
        self.reset()

    def reset(self):
        self.first = self.last = None
        self.hits = 0
        self.last_counted_hurt = None

    def observe(self, state, *, revision, native_idle):
        if self.triggered:
            return None
        if not isinstance(state, dict):
            self.reset()
            return None
        lease = state.get('supervision_lease') or {}
        hp, stamp, hurt, pos = (state.get(k) for k in
                                 ('health', 'time', 'recent_hurt_at', 'pos'))
        entities = state.get('entities')
        printer, build = state.get('professional_printer') or {}, state.get('build_job') or {}
        if not all(isinstance(v, dict) for v in (lease, printer, build)):
            self.reset()
            return None
        valid = (native_idle and state.get('connected') is True
                 and all(isinstance(v, str) and v for v in self.scope)
                 and (state.get('world_session'), lease.get('job_session'), lease.get('id')) == self.scope
                 and lease.get('world_session') == self.scope[0]
                 and lease.get('kind') in ('materials', 'parking')
                 and type(revision) is int and state.get('control_revision') == lease.get('revision') == revision
                 and type(hp) in (int, float) and math.isfinite(hp) and 0 < hp <= 20
                 and type(stamp) is int and type(hurt) is int and 0 < hurt <= stamp
                 and isinstance(pos, list) and len(pos) == 3
                 and all(type(v) in (int, float) and math.isfinite(v) for v in pos)
                 and isinstance(entities, list) and all(isinstance(e, dict) for e in entities)
                 and not any(e.get('hostile') is True and e.get('alive') is not False
                             and not (type(e.get('health')) in (int, float) and e['health'] <= 0)
                             for e in entities)
                 and state.get('manual_movement') is False and state.get('screen') == ''
                 and state.get('guard_armed') is True and state.get('guard_pve_only') is True
                 and not (state.get('safety_hold') or {}).get('active')
                 and not any(state.get(k) for k in ('interface_paused', 'navigating', 'native_material_busy',
                        'chopping', 'printing', 'borer_active', 'planter_active', 'feeder_active',
                        'fisher_active', 'air_return_active'))
                 and state.get('phase') != 'running'
                 and not any(printer.get(k) for k in ('owned', 'enabled', 'waiting_for_server'))
                 and not build.get('active'))
        if not valid:
            self.reset()
            return None
        if self.last and stamp <= self.last['time']:
            if stamp < self.last['time']:
                self.reset()
            return None
        environmental = state.get('recent_attacker') in ENVIRONMENTAL_ATTACKERS
        # A real escape or quiet interval is progress. Partial regeneration
        # must not erase repeated injury, including an unidentified source.
        if self.first and (math.dist(pos, self.first['pos']) > .75
                           or stamp-self.last['recent_hurt_at'] > 3500
                           or environmental != (self.first.get('recent_attacker') in ENVIRONMENTAL_ATTACKERS)):
            self.reset()
        sample = {k: state.get(k) for k in
                  ('time', 'health', 'pos', 'recent_hurt_at', 'recent_attacker', 'server', 'world_session')}
        sample['pos'] = list(pos)
        if stamp - hurt > 3000:
            self.reset()
            return None
        fresh_hit = self.last is None or hurt > self.last['recent_hurt_at'] and hp < self.last['health'] - .0001
        if self.first is None:
            if hp>=20:
                self.last=sample
                return None
            self.first, self.hits = sample, 1
            self.last_counted_hurt = hurt
        elif fresh_hit and (not environmental or hurt-self.last_counted_hurt>=500):
            self.hits += 1
            self.last_counted_hurt = hurt
        self.last = sample
        elapsed = stamp-self.first['time']
        environmental_exit = (environmental and fresh_hit and self.hits >= 2 and elapsed >= 500)
        generic_exit = (fresh_hit and self.hits >= 4 and elapsed >= 10_000
                        and hp < self.first['health'] - .0001)
        if environmental_exit or generic_exit:
            self.triggered = True
            return {'first': self.first, 'latest': sample, 'distinct_damage_events': self.hits,
                    'stationary_seconds': (stamp - self.first['time']) / 1000,
                    'stationary_radius': .75, 'observed_loaded_hostiles': 0,
                    'environmental_damage': environmental_exit,
                    'automatic_reconnect_allowed': False}
        return None
