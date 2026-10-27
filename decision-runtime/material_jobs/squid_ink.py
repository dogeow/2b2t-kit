"""One observed wild squid, normal guarded diving attacks and actual matching ink."""
import math
import time
from pathlib import Path

from kit_runtime.journal import write_json
from .acquisition import block_id, carried
from .navigation import settled_state
from .protocol import JobBlocked

def observed_live(client,uuid,species,q):
    current=next((e for e in q.get('entities',[])if e.get('uuid')==uuid),None)
    if current is not None:return current if current.get('type')==species and current.get('has_custom_name')is False and current.get('health',0)>0 else None
    found=None
    if species=='minecraft:glow_squid'and getattr(client,'root',None)is not None:
        from .loaded_squid_survey import read_glow
        found=next((e for e in read_glow(client.root,q)if e['uuid']==uuid),None)
    return found


def collect(client, candidate, directory, checkpoint):
    species=candidate.get('type')
    pairs={'minecraft:squid':('minecraft:ink_sac',2),
           'minecraft:glow_squid':('minecraft:glow_ink_sac',3)}
    if species not in pairs:raise JobBlocked('只采集当前已观察到的野生鱿鱼或发光鱿鱼')
    ink,protocol=pairs[species]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'squid-ink.json'
    if path.exists():
        raise JobBlocked('保留原鱿鱼采集回执，不重放')
    book = {'world_session': client.world, 'uuid': candidate['uuid'],'species':species,'ink_item':ink,
            'attacks': [], 'pending': None, 'actual_ink_gain': 0, 'complete': False}
    write_json(path, book)
    before = carried(checkpoint(), ink)

    def state():
        q = checkpoint()
        if q.get('health', 0) < 19 or q.get('guard_busy'):
            raise JobBlocked('潜水生命或防护状态变化')
        return q

    def live(q):
        return observed_live(client,candidate['uuid'],species,q)

    def arm_air(q):
        if not q.get('under_water'):
            return q
        target = [q['pos'][0], 65.0, q['pos'][2]]
        client.checked('air_return_set', target=target)
        book.setdefault('air_return_sets', []).append({'target': target, 'request_id': client.last})
        write_json(path, book)
        return state()

    def water_route(target):
        q = state(); start = q['pos']
        lo = [math.floor(min(start[0], target[0]) - .31),
              math.floor(min(start[1], target[1])),
              math.floor(min(start[2], target[2]) - .31)]
        hi = [math.floor(max(start[0], target[0]) + .31),
              math.floor(max(start[1], target[1]) + 1.8),
              math.floor(max(start[2], target[2]) + .31)]
        total = math.prod(b-a+1 for a, b in zip(lo, hi))
        if total > 8192:
            raise JobBlocked('潜水通道超出局部范围')
        r = client.request('scan', min=lo, max=hi, details=True)
        if (r.get('phase') != 'done' or r.get('world_session') != client.world
                or r.get('scan_cells_read') != total or r.get('scan_total_cells') != total):
            raise JobBlocked('潜水身体通道扫描未确认')
        water = {'minecraft:water', 'minecraft:kelp', 'minecraft:kelp_plant',
                 'minecraft:seagrass', 'minecraft:tall_seagrass'}
        if any(block_id(row) not in water or row.get('block_entity')
               for row in r.get('blocks', [])):
            raise JobBlocked('潜水身体通道有实物或危险方块，不挖掘绕过')

    def swim(target, descending=False):
        q = state()
        if q.get('air_supply', 0) < q.get('air_pickup_floor', 260):
            raise JobBlocked('潜水余量到达返回阈值')
        # Keep every horizontal leg inside the native air route's 3-block
        # ownership radius; refresh its real vertical column after each leg.
        distance = math.hypot(target[0]-q['pos'][0], target[2]-q['pos'][2])
        if distance > 1.75 and q.get('under_water'):
            segments = math.ceil(distance/1.75)
            start = list(q['pos'])
            for i in range(1, segments+1):
                point = [start[0]+(target[0]-start[0])*i/segments,
                         q['pos'][1], start[2]+(target[2]-start[2])*i/segments]
                q = swim(point)
            return q
        water_route(target)
        book['pending'] = {'kind': 'swim', 'target': target}
        write_json(path, book)
        if q.get('under_water'):
            # Keep Meteor Flight enabled for chasing a swimming target.
            # The complete water-body sweep and native air route were proved
            # above; ordinary navigation preserves its normal game inputs.
            r = client.request('navigate', target=target, arrival=.4, seconds=15)
        else:
            r = client.request('walk', target=target, arrival=.25,
                               restore_flight=True, seconds=15)
        if r.get('phase') != 'done':
            raise JobBlocked('原潜水移动未确认，不重发')
        book['pending'] = None
        write_json(path, book)
        return arm_air(state())

    def surface():
        q = checkpoint()
        if q.get('air_return_active'):
            until = time.monotonic()+20
            while q.get('under_water') and time.monotonic() < until:
                time.sleep(.1); q = checkpoint()
            if q.get('under_water'):
                raise JobBlocked('原生自动返气尚未确认，不重复导航')
            book['native_auto_surface_confirmed'] = True
            write_json(path, book)
        if q['pos'][1] >= 63 and not q.get('under_water'):
            return
        target = [q['pos'][0], 64.2, q['pos'][2]]
        water_route(target)
        r = client.request('navigate', target=target, arrival=.2, seconds=30)
        if r.get('phase') != 'done':
            raise JobBlocked('原返气移动未确认，不重发')
        until = time.monotonic()+4
        q = state()
        while (q.get('under_water') or q.get('air_supply', 0) < q.get('max_air_supply', 300)) and time.monotonic() < until:
            time.sleep(.1); q = state()
        if q.get('under_water') or q.get('air_supply', 0) < q.get('max_air_supply', 300):
            raise JobBlocked('实际返气位置未确认')
        book['surface_confirmed'] = True
        write_json(path, book)

    try:
        q = state()
        if q.get('material_ink_attack_protocol', 0) < protocol:
            raise JobBlocked('当前主插件尚未支持有氧水下鱿鱼近战')
        p = candidate['pos']; top = [p[0], 63.2, p[2]]
        client.checked('navigate', target=top, arrival=.15, air_only=True, seconds=45)
        settled_state(client, top, .45)
        client.checked('select_item', item='minecraft:netherite_sword')
        old_items = {e['uuid'] for e in state().get('entities', []) if e.get('type') == 'minecraft:item'}
        q = swim([p[0], 60.0, p[2]])
        if not q.get('under_water'):
            raise JobBlocked('正常入水位置未确认')
        deadline = time.monotonic() + 30
        for hit in range(3):
            q = state(); e = live(q)
            if not e or time.monotonic() >= deadline:
                break
            target = [e['pos'][0], q['pos'][1], e['pos'][2]]
            if math.hypot(target[0]-q['pos'][0], target[2]-q['pos'][2]) > .5:
                q = swim(target)
            for _ in range(4):
                e = live(q)
                if not e:
                    break
                desired = e['pos'][1] + .2
                if q['pos'][1] - desired < .5:
                    break
                target = [q['pos'][0], max(desired, q['pos'][1]-4), q['pos'][2]]
                q = swim(target, descending=True)
            q = state(); e = live(q)
            if not e:
                break
            distance = math.dist([q['pos'][0], q['pos'][1]+1.62, q['pos'][2]],
                                 [e['pos'][0], e['pos'][1]+.4, e['pos'][2]])
            while distance > 2.75 and time.monotonic() < deadline:
                # Deep glow targets still use bounded vertical steps and the
                # current native oxygen/return budget before every next move.
                target = [e['pos'][0], max(e['pos'][1]+.2,q['pos'][1]-4), e['pos'][2]]
                q = swim(target)
                e = live(q)
                if not e:
                    break
                distance = math.dist([q['pos'][0], q['pos'][1]+1.62, q['pos'][2]],
                                     [e['pos'][0], e['pos'][1]+.4, e['pos'][2]])
            if not e or distance > 2.75:
                break
            until = time.monotonic()+2
            while state().get('attack_strength', 0) < .95 and time.monotonic() < until:
                time.sleep(.1)
            center = [math.floor(v) for v in e['pos']]
            health_before = e['health']
            book['pending'] = {'kind': 'attack', 'uuid': e['uuid'], 'health_before': health_before}
            write_json(path, book)
            r = client.request('material_ink_attack', entity_id=e['id'], expected_uuid=e['uuid'],
                               region_min=[v-4 for v in center], region_max=[v+4 for v in center])
            proof = r.get('ink_attack') or {}
            if proof.get('pre_dispatch_rejected') is True and proof.get('action_sent') is False:
                book['pending'] = None; book['rejected'] = proof; write_json(path, book)
                break
            if r.get('phase') != 'done' or proof.get('action_sent') is not True:
                raise JobBlocked('原鱿鱼攻击未确认，不重发')
            until = time.monotonic()+3
            while time.monotonic() < until:
                q = state(); after = live(q)
                if after is None or after['health'] < health_before:
                    break
                time.sleep(.1)
            else:
                raise JobBlocked('已派发攻击未观察到生命变化，不再次攻击')
            book['attacks'].append({'request_id': client.last, 'proof': proof, 'after': after})
            book['pending'] = None; write_json(path, book); time.sleep(.7)
        until = time.monotonic()+6
        while time.monotonic() < until:
            q = state()
            drops = [e for e in q.get('entities', []) if e.get('type') == 'minecraft:item'
                     and e['uuid'] not in old_items and e.get('stack', {}).get('item') == ink]
            if drops or carried(q, ink) > before:
                break
            time.sleep(.1)
        for drop in drops:
            q = state(); baseline = carried(q, ink)
            if math.dist(q['pos'], drop['pos']) > 8:
                continue
            target = [drop['pos'][0], q['pos'][1], drop['pos'][2]]
            q = swim(target)
            live_drop = next((e for e in q.get('entities', []) if e.get('uuid') == drop['uuid']), None)
            if live_drop and q['pos'][1]-live_drop['pos'][1] >= .5:
                target = [q['pos'][0], max(live_drop['pos'][1]-.2, q['pos'][1]-4), q['pos'][2]]
                q = swim(target, descending=True)
            until = time.monotonic()+2
            while carried(state(), ink) == baseline and time.monotonic() < until:
                time.sleep(.1)
        book['actual_ink_gain'] = carried(state(), ink)-before
        surface()
        book['complete'] = book['actual_ink_gain'] > 0
        write_json(path, book)
        return book
    except Exception:
        if (getattr(client, 'native_inflight', None) is None
                and getattr(client,'unconfirmed_native_request',None) is None):
            surface()
        raise
