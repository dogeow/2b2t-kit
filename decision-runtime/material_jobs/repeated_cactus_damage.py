"""Detect distinct fresh cactus hits while the exact failed task still owns cleanup."""


class RepeatedCactusDamage:
    def __init__(self, world, task, lease):
        self.world, self.task, self.lease = world, task, lease
        self.hits = []

    def observe(self, state):
        lease = state.get('supervision_lease') or {}
        if (state.get('connected') is not True or state.get('world_session') != self.world
                or state.get('manual_movement') or state.get('screen')
                or lease.get('id') != self.lease or lease.get('job_session') != self.task
                or lease.get('world_session') != self.world or lease.get('kind') != 'materials'
                or lease.get('revision') != state.get('control_revision')):
            self.hits.clear()
            return False
        now, hurt = state.get('time'), state.get('recent_hurt_at')
        if (type(now) is not int or type(hurt) is not int or hurt <= 0
                or not 0 <= now-hurt <= 5000):
            return False
        if str(state.get('recent_attacker', '')).strip().lower() not in ('仙人掌', 'cactus', 'minecraft:cactus'):
            self.hits.clear()
            return False
        if self.hits and hurt < self.hits[-1]['hurt_at']:
            self.hits.clear()
            return False
        self.hits = [hit for hit in self.hits if 0 <= hurt-hit['hurt_at'] <= 30000]
        if not self.hits or self.hits[-1]['hurt_at'] != hurt:
            self.hits.append({'hurt_at': hurt, 'observed_at': now,
                             'health': state.get('health'), 'pos': state.get('pos')})
        return len(self.hits) >= 2
