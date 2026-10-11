"""Opt-in flat-map construction adapter for the existing material scheduler.

No new action controller, configuration change or automatic job launch. Supply,
recipes, processing, control and parking stay with the existing Backend. Every
window retains its journal until native ACK, physical cells and stock agree.
"""
import json
import math
from collections import Counter
from pathlib import Path
import time

from kit_runtime.journal import write_json
from material_jobs.protocol import JobBlocked
from material_jobs_backend import Backend
from material_plan import inventory_counts
from projection_flat_plan import FlatLayout, next_batch, policy, position, full_block, plain_mushroom_stem, vertical_deepslate
from projection_patch_plan import connected_mask
from projection_scene_lights import registered_map_light, neighbour_map_light
from projection_completion import block_state
from projection_flat_cache import FlatMaterialLedger


def printer_sent_nothing(reply, client):
    """A terminal native interval with no proposal is distinct from unknown ACK."""
    pp=reply.get('professional_printer')or{}
    return (reply.get('phase')=='waiting' and reply.get('op')=='professional_print'
            and reply.get('detail')=='printer interval ended without complete current bounded-mask server confirmation'
            and reply.get('world_session')==client.world and reply.get('control_revision')==client.rev
            and reply.get('id')==client.last and bool(client.last)
            and isinstance(pp,dict) and pp.get('last_proposal')=={} and pp.get('failure')==''
            and all(type(pp.get(k))is int and pp[k]==0 for k in
                    ('server_confirmed','fast_proposals','complex_proposals','travel_pending'))
            and all(pp.get(k)is False for k in ('owned','enabled','waiting_for_server')))


def scene(layout, reply, low, high, world, revision):
    """Accept a complete bounded native scan, including explicit light rules."""
    volume = math.prod(b - a + 1 for a, b in zip(low, high))
    if (reply.get('phase') != 'done' or reply.get('world_session') != world
            or type(reply.get('scan_cells_read')) is not int or reply['scan_cells_read'] != volume
            or type(reply.get('scan_total_cells')) is not int or reply['scan_total_cells'] != volume
            or any(type(reply.get(k)) is not int or reply[k] != revision
                   for k in ('control_revision', 'scan_start_revision', 'scan_end_revision'))
            or not isinstance(reply.get('blocks'), list)):
        raise JobBlocked('地图画局部扫描未完整确认；保留当前窗口')
    observed = {}
    for row in reply['blocks']:
        p = position(row.get('pos'))
        if p in observed or any(n < a or n > b for n, a, b in zip(p, low, high)):
            raise JobBlocked('地图画扫描含重复或越界坐标')
        observed[p] = row
    actual = {}
    registered_lights = layout.config['registered_lights']
    if layout.config.get('reuse_existing_map_lights') is True:
        registered_lights |= {p for p, row in observed.items()
                              if registered_map_light(row, layout.expected, observed, {p}, layout.low[1])}
    for p, row in observed.items():
        if p[1] != layout.low[1]:
            if (registered_map_light(row, layout.expected, observed, registered_lights, layout.low[1])
                    or neighbour_map_light(row, layout.expected, observed, layout.low[1])):
                continue
            raise JobBlocked('地图画站位上方存在未登记方块；先核对现场')
        if any(row.get(k) is not False for k in ('fluid', 'block_entity')):
            raise JobBlocked('地图画扫描发现液体或容器；保留现场')
        if p not in layout.expected:
            continue  # Neighbour terrain is never a repair target or inferred model support.
        if row.get('state') != layout.expected[p]['state'] or row.get('solid') is not True:
            raise JobBlocked('图面已有方块与模型不一致；使用已有专用修复工序')
        actual[p] = row['state']
    return actual


def accept_window(plan, before, after, stock_before, stock_after, receipt, expected):
    mask = {position(p) for p in plan['positions']}
    changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
    if (not changed or not changed <= mask or changed & before.keys()
            or any(after.get(p) != expected[p]['state'] for p in changed)
            or type(stock_before) is not int or type(stock_after) is not int
            or stock_before - stock_after != len(changed) or receipt.get('phase') != 'done'):
        raise JobBlocked('窗口方块、物资消耗或原生结果不一致；不重复发送')
    if plan['operation'] == 'print':
        pp = receipt.get('professional_printer', {})
        if (type(pp.get('server_confirmed')) is not int or pp['server_confirmed'] != len(changed)
                or pp.get('failure') != '' or pp.get('travel_pending') != 0
                or any(pp.get(k) is not False for k in ('owned', 'enabled', 'waiting_for_server'))):
            raise JobBlocked('打印窗口仍有未知结果；保留原回执')
    else:
        ack = receipt.get('projection_air_seed', {})
        target = plan['positions'][0]
        if (changed != {position(target)} or ack.get('target') != target
                or ack.get('server_confirmed') is not True or ack.get('projection_matches') is not True
                or ack.get('requires_stripping') is not False or type(ack.get('use_count')) is not int or ack['use_count'] != 1
                or ack.get('expected_state') != expected[position(target)]['state']
                or ack.get('projected_state') != expected[position(target)]['state']
                or type(ack.get('inventory_before')) is not int or ack['inventory_before'] != stock_before
                or type(ack.get('inventory_after')) is not int or ack['inventory_after'] != stock_after):
            raise JobBlocked('隔空起始块缺少完整原生确认；不重复发送')
    return changed


class FlatMapBackend(Backend):
    PROJECTION_LOADING_RADIUS=48

    def _release_no_effect_print(self,client,layout,plan,directory,journal,reply,before,stock_before):
        if plan['operation']!='print' or not printer_sent_nothing(reply,client):return False
        state=self._safe_flat(client,layout)
        after,_,_=self._scan_flat(client,layout,plan,directory,'no-effect')
        if (after!=before or inventory_counts(state).get(plan['item'],0)!=stock_before
                or inventory_counts(self._safe_flat(client,layout)).get(plan['item'],0)!=stock_before):
            raise JobBlocked('零提案打印的现场或物资已变化；保留原窗口')
        cleared=client.checked('projection_batch_clear',placement_key=layout.key)
        write_json(directory/'no-effect-clear-receipt.json',cleared)
        if cleared.get('projection_batch',{}).get('active')is not False:
            raise JobBlocked('零提案打印掩码未清除；保留原窗口')
        journal.update(pending=None,no_effect_verified=True,placement_credit=0,
                       inventory_before=stock_before,inventory_after=stock_before)
        write_json(directory/'flat-window.json',journal)
        return True

    def refresh_audit(self):
        """Wait for the entire server map at the already verified loading pose."""
        client=self.ensure_client();previous=self.busy;self.busy=True
        try:
            for attempt in range(20):
                reply=client.request('projection_audit');value=reply.get('projection_audit')or{}
                if reply.get('world_session')!=client.world:
                    raise JobBlocked('地图画完整审计的世界或原模型已变化')
                if not value and reply.get('phase')=='error':
                    # Native audit throws before returning a model while its
                    # schematic chunks are still arriving. Re-observe only
                    # this known read failure under the same exact selection.
                    if (reply.get('detail','').startswith('等待图纸区块 ')
                            and (reply.get('projection_selection')or{}).get('key')==self.request['projection_key']):
                        self.checkpoint()
                        if attempt<19:time.sleep(.25)
                        continue
                    raise JobBlocked(reply.get('detail')or'地图画完整审计读取失败')
                if value.get('placement_key')!=self.request['projection_key']:
                    raise JobBlocked('地图画完整审计的世界或原模型已变化')
                if(value.get('loaded_chunks_verified')is True and value.get('loaded_server_chunks_verified')is True
                        and not(value.get('kinds')or{}).get('unloaded')):
                    self.audit=value;self.audit_dirty=False;write_json(self.out/'projection-latest.json',value);return value
                self.checkpoint()
                if attempt<19:time.sleep(.25)
            raise JobBlocked('地图画完整服务器区块仍未加载；不按旧差料施工')
        finally:self.busy=previous

    def __init__(self, request, automation, out, checkpoint):
        if request.get('mode') != 'projection':
            raise ValueError('Flat-map adapter requires an explicit projection task')
        policy(request.get('flat_map'))  # Validate before constructing the existing backend.
        super().__init__(request, automation, out, checkpoint)
        from projection_flat_continuity import restore
        restore(self, self.latest)

    def observe(self):
        state = super().observe()
        ledger = getattr(self, 'flat_ledger', None)
        if (ledger is not None and (ledger.audit.get('material_ledger') or getattr(self, 'parked_ledger_reused', False))
                and not ledger.audit['mismatches']
                and not self.busy and not self.checking and not self.cleaning):
            # Never let the scheduler complete a projection from cached totals.
            audit = self.refresh_audit()
            self.flat_ledger = FlatMaterialLedger(ledger.layout, audit, ledger.world)
            state = dict(state, projection_audit=audit)
            self.latest = state
        return state

    def _layout(self, client, projection_key, out):
        layout = getattr(self, 'flat_layout', None)
        if layout is not None:
            selection = client.status().get('projection_selection', {})
            if (layout.key != projection_key or selection.get('key') != layout.key
                    or position(selection.get('min')) != layout.low
                    or position(selection.get('max')) != layout.high):
                raise JobBlocked('地图画缓存模型的选择范围已改变')
            return layout
        for attempt in range(40):
            reply = client.request('projection_model')
            write_json(out / 'flat-model.json', reply)
            if reply.get('world_session') != client.world:
                raise JobBlocked('地图画模型读取期间世界已改变')
            model = reply.get('projection_model', {})
            if (model.get('loaded_chunks_verified') is True
                    and model.get('loaded_server_chunks_verified') is True):
                break
            self.checkpoint()
            if attempt == 39:
                raise JobBlocked('地图画区块仍未完整加载；不规划或发送施工')
            time.sleep(.25)
        layout = FlatLayout(model, self.request['flat_map'])
        if layout.key != projection_key:
            raise JobBlocked('地图画目标投影已改变')
        self.flat_layout = layout
        self.flat_model = model
        return layout

    def try_direct_registered_travel(self, client, target, checkpoint, trace, *, keep_cruise):
        """Vertical departure, then a straight line to the registered work area.

        Native swept-volume limits still apply. Collinear legs remain below
        that limit; no axis detours or repeated broad Python corridor scans.
        """
        if self.request['flat_map'].get('direct_registered_map_routes') is not True:
            return False
        state = client.status(); selection = state.get('projection_selection') or {}
        station = self.profile.get('mud_station') or {}
        work = station.get('pos')
        if (selection.get('key') != self.request['projection_key'] or station.get('authorized') is not True
                or not isinstance(work, list) or len(work) != 3):
            return False
        low, high = selection.get('min'), selection.get('max')
        if not low or not high:
            return False
        on_map = lambda p: low[0]-3 <= p[0] <= high[0]+4 and low[2]-3 <= p[2] <= high[2]+4
        anchors = [[work[0]+.5, work[1]+1, work[2]+.5]]
        for name in ('workbench_staging', 'supply_staging', 'park_target'):
            point = self.profile.get(name)
            if (isinstance(point, list) and len(point)==3
                    and all(type(v) in (int,float) and math.isfinite(v) for v in point)):
                anchors.append(point)
        at_work = lambda p: any(math.hypot(p[0]-a[0], p[2]-a[2]) <= 6 for a in anchors)
        here = state['pos']
        within_map=(self.request['flat_map'].get('direct_within_map_windows')is True
                    and on_map(here)and on_map(target))
        if (not (within_map or on_map(here) and at_work(target) or at_work(here) and on_map(target))
                or min(here[1], target[1]) < high[1]+2
                or math.dist(here, target) > 256):
            return False
        from material_jobs.navigation import settled_state

        def move(point, event, segment):
            checkpoint()
            before = list(client.status()['pos'])
            reply = client.request('navigate', target=point, arrival=.25, air_only=True, seconds=45)
            trace.append({'event': event, 'segment': segment, 'from': before,
                          'target': point, 'final_target': list(target), 'native_reply': reply})
            if reply.get('phase') != 'done':
                raise JobBlocked('登记地图直线航段未确认；不重放导航')
            settled_state(client, point, .55)

        # A window is close to the image while the work-area approach is high.
        # Handle that height difference at the origin instead of falling back
        # to the X-then-Z route. Every vertical leg retains native body checks.
        cruise = max(here[1], target[1])if within_map else max(here[1], target[1], high[1]+8)
        for segment in range(8):
            checkpoint(); here = client.status()['pos']
            if cruise-here[1] <= .55:
                break
            move([here[0], min(cruise, here[1]+48), here[2]],
                 'direct_registered_map_ascent', segment+1)
        else:
            raise JobBlocked('登记地图起飞航段上限已到，保留原目标')
        destination = [target[0], cruise, target[2]]
        for segment in range(8):
            checkpoint(); here = client.status()['pos']; distance = math.dist(here, destination)
            if distance <= .55:
                break
            ratio = min(1., 48 / distance)
            point = [a + (b-a)*ratio for a, b in zip(here, destination)]
            while math.prod(abs(b-a)+padding for a,b,padding in zip(here,point,(1.6,2.8,1.6)))>8000:
                ratio*=.75
                point = [a+(b-a)*ratio for a,b in zip(here,destination)]
            # Preserve the native8192-cell swept-volume gate, including a
            # conservative player/body margin for mildly sloped staging legs.
            move(point, 'direct_registered_map_segment', segment+1)
        else:
            if math.dist(client.status()['pos'], destination) > .55:
                raise JobBlocked('登记地图直线航段上限已到，保留原目标')
        if keep_cruise:
            return True
        for segment in range(8):
            checkpoint(); here = client.status()['pos']
            if math.dist(here, target) <= .55:
                return True
            move([target[0], max(target[1], here[1]-48), target[2]],
                 'direct_registered_map_descent', segment+1)
        if math.dist(client.status()['pos'], target) <= .55:
            return True
        raise JobBlocked('登记地图下降航段上限已到，保留原目标')

    def _ledger(self, client, layout):
        ledger = getattr(self, 'flat_ledger', None)
        if ledger is not None and ledger.world != client.world:
            raise JobBlocked('地图画实际缓存属于旧连接；需要独立的新任务')
        if (ledger is None or getattr(self, 'audit_dirty', True)
                or ledger.audit is not getattr(self, 'audit', None)):
            audit = getattr(self, 'audit', None)
            if audit is None or getattr(self, 'audit_dirty', True):
                audit = self.refresh_audit()
            ledger = FlatMaterialLedger(layout, audit, client.world)
            self.flat_ledger = ledger
        return ledger

    def has_ready_projection_output(self, snapshot):
        """Read-only offer: spend plain carried stock before any supply trip."""
        audit = snapshot.get('projection_audit', {})
        if (snapshot.get('projection_selection', {}).get('key') != self.request['projection_key']
                or snapshot.get('projection_air_seed_protocol') != 1
                or audit.get('placement_key') != self.request['projection_key']
                or audit.get('loaded_chunks_verified') is not True
                or audit.get('loaded_server_chunks_verified') is not True):
            return False
        rows = snapshot.get('inventory', [])
        if len(rows) != 43 or {r.get('slot') for r in rows} != set(range(43)):
            return False
        usable=Counter()
        for r in rows:
            if (set(r)=={'slot','item','count','max_stack'}and r['slot']<36 and type(r['count'])is int
                    and type(r['max_stack'])is int and 2<r['count']<=r['max_stack']):usable[r['item']]+=r['count']
        minimum=getattr(self,'profile',{}).get('minimum_projection_trip_stack',3)
        if type(minimum)is not int or not 3<=minimum<=64:
            raise JobBlocked('地图材料单次返图数量登记无效')
        excluded = policy(self.request['flat_map'])['excluded_positions']
        needed={}
        for row in audit.get('mismatches', []):
            item, _ = block_state(row.get('expected', ''))
            if item not in usable:
                continue
            if (row.get('kind') == 'missing' and row.get('actual') in
                    ('Block{minecraft:air}','Block{minecraft:cave_air}','Block{minecraft:void_air}')
                    and all(row.get(k) is False for k in ('fluid','adjacent_fluid','block_entity'))
                    and row.get('neighbors_loaded') is True
                    and position(row['pos']) not in excluded
                    and (not plain_mushroom_stem(row['expected'],item)
                         or snapshot.get('projection_mushroom_stem_seed_protocol')==1)
                    and (not vertical_deepslate(row['expected'],item)
                         or snapshot.get('projection_air_seed_axis_protocol')==1)
                    and full_block(row['expected'], item)):
                needed[item]=needed.get(item,0)+1
        return any(usable[item]>=min(minimum,count+2)for item,count in needed.items())

    def _safe_flat(self, client, layout):
        self.checkpoint()
        state = client.status()
        lease = state.get('supervision_lease', {})
        printer = state.get('professional_printer', {})
        if (state.get('connected') is not True or state.get('world_session') != client.world
                or state.get('projection_selection', {}).get('key') != layout.key
                or state.get('control_revision') != client.rev
                or state.get('health') != 20 or state.get('food', 0) < 18
                or state.get('manual_movement') is not False or state.get('screen') != ''
                or state.get('guard_busy') is not False or state.get('under_water') is not False
                or state.get('safety_hold', {}).get('active') is not False
                or any(state.get(k) is not True for k in ('flight', 'guard_armed', 'guard_pve_only'))
                or lease.get('kind') != 'materials' or lease.get('id') != client.heartbeat.id
                or lease.get('job_session') != client.task or lease.get('world_session') != client.world
                or lease.get('revision') != client.rev
                or any(state.get(k) for k in ('navigating', 'printing', 'borer_active', 'chopping'))
                or state.get('build_job', {}).get('active')
                or state.get('phase') == 'running'
                or getattr(client, 'native_inflight', None) is not None
                or getattr(client, 'unconfirmed_native_request', None) is not None
                or printer.get('owned') is not False or printer.get('enabled') is not False
                or printer.get('waiting_for_server') is not False or printer.get('travel_pending') != 0
                or printer.get('rotate') is not True or printer.get('in_air') is not False
                or printer.get('air_place') is not False):
            raise JobBlocked('当前角色、工作回执或打印设置不适合新地图画窗口')
        state = dict(state, target_stack_sizes=self.request.get('target_stack_sizes', {}))
        return state

    def _scan_flat(self, client, layout, plan, directory, label):
        low = [plan['patch_min'][0] - 1, layout.low[1], plan['patch_min'][2] - 1]
        high = [plan['patch_max'][0] + 1, layout.low[1] + 4, plan['patch_max'][2] + 1]
        reply = client.request('scan', min=low, max=high, details=True)
        write_json(directory / (label + '-scan.json'), reply)
        return scene(layout, reply, low, high, client.world, client.rev), low, high

    def _stock_after(self, client, layout, item, expected, minimum_time):
        end = time.monotonic() + 4
        last_time, samples = minimum_time, 0
        while time.monotonic() < end:
            client.request('snapshot')
            state = self._safe_flat(client, layout)
            if inventory_counts(state).get(item, 0) != expected:
                samples = 0
            elif type(state.get('time')) is int and type(last_time) is int and state['time'] > last_time:
                samples += 1
                last_time = state['time']
                if samples == 2:
                    return state
            time.sleep(.1)
        raise JobBlocked('地图画窗口物资尚未稳定确认；保留原请求')

    def _window(self, client, layout, actual, plan, directory):
        from material_jobs.acquisition import _travel
        started = time.monotonic()
        self._safe_flat(client, layout)
        if client.status().get('projection_batch', {}).get('active'):
            raise JobBlocked('既有施工掩码尚未清除；不覆盖它')
        directory.mkdir()
        journal = {'schema': 1, 'world_session': client.world, 'task_session': client.task,
                   'placement_key': layout.key, 'plan': plan, 'complete': False, 'pending': 'navigate'}
        save = lambda: write_json(directory / 'flat-window.json', journal)
        save()
        trace = []
        here = client.status()['pos']
        if math.dist(here, plan['station']) <= .15:
            trace.append({'event': 'already_at_map_station'})
        elif (math.hypot(here[0] - plan['station'][0], here[2] - plan['station'][2]) <= 12
                and abs(here[1] - plan['station'][1]) <= 1):
            # The native air-only navigator validates collision/clearance. A
            # nearby map window needs no ground-to-high-cruise departure.
            reply = client.request('navigate', target=plan['station'], arrival=.15,
                                   air_only=True, seconds=25)
            trace.append({'event': 'nearby_map_air_navigation', 'reply': reply})
            if reply.get('phase') != 'done':
                write_json(directory / 'travel.json', trace)
                raise JobBlocked('近处地图画站位未确认；不重放导航或放置')
        else:
            _travel(client, plan['station'], self.checkpoint, trace, keep_cruise=False)
        write_json(directory / 'travel.json', trace)
        travel_seconds = time.monotonic() - started
        state = self._safe_flat(client, layout)
        if math.dist(state['pos'], plan['station']) > .75:
            raise JobBlocked('地图画施工站位尚未实际到达；不设置掩码或消耗材料')
        before, low, high = self._scan_flat(client, layout, plan, directory, 'before')
        previous = {p: v for p, v in actual.items() if all(a <= n <= b for n, a, b in zip(p, low, high))}
        if previous != before:
            raise JobBlocked('局部现场已变化；原窗口保持停止，重新审计后才能规划')
        mask = [position(p) for p in plan['positions']]
        if set(mask) & before.keys() or set(mask) & layout.config['excluded_positions']:
            raise JobBlocked('当前窗口包含已占用或保留坐标')
        client.checked('select_item', item=plan['item'], slot=plan['slot'])
        state = self._safe_flat(client, layout)
        selected = next((r for r in state['inventory'] if r['slot'] == state.get('selected_slot')), {})
        if (set(selected) != {'slot', 'item', 'count', 'max_stack'}
                or selected.get('item') != plan['item'] or selected.get('count', 0) < len(mask) + 2
                or state.get('hand', {}).get('item') != plan['item']):
            raise JobBlocked('实际手持堆叠或保留数量不符合窗口计划')
        stock_before = inventory_counts(state).get(plan['item'], 0)
        if plan['operation'] == 'print':
            ordered = connected_mask(set(mask), actual, plan['patch_min'], plan['patch_max'], len(mask),
                                     excluded=layout.config['excluded_positions'])
            if set(ordered) != set(mask):
                raise JobBlocked('当前实际支撑不能覆盖整个打印窗口')
            journal['pending'] = 'projection_batch_set'
            save()
            reply = client.checked('projection_batch_set', placement_key=layout.key,
                                   positions=plan['positions'], min_feet_y=layout.low[1] + 1)
            write_json(directory / 'mask-receipt.json', reply)
            scope = reply.get('projection_batch', {})
            if (scope.get('active') is not True or scope.get('count') != len(mask)
                    or scope.get('placement_key') != layout.key or scope.get('task_session') != client.task
                    or scope.get('min_feet_y') != layout.low[1] + 1):
                raise JobBlocked('地图画有界掩码未确认')
            journal['pending'] = 'professional_print'
            save()
            reply = client.request('professional_print', seconds=min(30, math.ceil(len(mask) * 1.4 + 4)))
        else:
            journal['pending'] = 'projection_air_seed'
            save()
            p = mask[0]
            reply = client.request('projection_air_seed', placement_key=layout.key, target=list(p),
                                   expected_item=plan['item'], expected_state=layout.expected[p]['state'])
        write_json(directory / 'native-receipt.json', reply)
        # Confirm settled native output before any new inventory read or cleanup.
        if reply.get('phase') != 'done':
            if self._release_no_effect_print(client,layout,plan,directory,journal,reply,before,stock_before):
                raise JobBlocked('打印器未发出放置提案；已核验零消耗并清除本窗口，正常高空收尾')
            raise JobBlocked('地图画原生窗口未结束；保留回执，不重放')
        if plan['operation'] == 'print':
            pp = reply.get('professional_printer', {})
            count = pp.get('server_confirmed')
            if (type(count) is not int or not 1 <= count <= len(mask) or pp.get('failure') != ''
                    or pp.get('travel_pending') != 0
                    or any(pp.get(k) is not False for k in ('owned', 'enabled', 'waiting_for_server'))):
                raise JobBlocked('打印回执不完整；保留当前窗口')
        else:
            count = 1
        journal['pending'] = 'physical_and_stock_verification'
        save()
        stable = self._stock_after(client, layout, plan['item'], stock_before - count, reply.get('time'))
        after, _, _ = self._scan_flat(client, layout, plan, directory, 'after')
        if inventory_counts(self._safe_flat(client, layout)).get(plan['item'], 0) != stock_before - count:
            raise JobBlocked('物资在窗口物理复核后变化；保留原回执')
        changed = accept_window(plan, before, after, stock_before,
                                inventory_counts(stable).get(plan['item'], 0), reply, layout.expected)
        if plan['operation'] == 'print':
            journal['pending'] = 'projection_batch_clear'
            save()
            cleared = client.checked('projection_batch_clear', placement_key=layout.key)
            write_json(directory / 'clear-receipt.json', cleared)
            if cleared.get('projection_batch', {}).get('active') is not False:
                raise JobBlocked('窗口结束但掩码清除未确认')
        journal.update(pending=None, complete=True, physical_positions=[list(p) for p in sorted(changed)],
                       inventory_before=stock_before, inventory_after=stock_before - len(changed),
                       elapsed_seconds=time.monotonic()-started, travel_seconds=travel_seconds)
        save()
        try:
            from projection_efficiency import WindowEfficiency
            if not hasattr(self, 'window_efficiency'):
                self.window_efficiency = WindowEfficiency()
            review = self.window_efficiency.add(journal)
            if review is not None:
                write_json(self.out / 'efficiency-review.json', review)
        except (OSError, ValueError, TypeError, AttributeError):
            pass  # Diagnostics must not interrupt a proved placement or ask for a retry.
        return after, len(changed)

    def build(self, projection_key):
        with self.action('build') as (client, out):
            self.prepare_travel()
            state = client.status()
            selection = state.get('projection_selection', {})
            low, high = position(selection.get('min')), position(selection.get('max'))
            if selection.get('key') != projection_key or any(a > b for a, b in zip(low, high)):
                raise JobBlocked('地图画当前选择范围已改变；不使用旧模型')
            center = [(low[0] + high[0] + 1) / 2, max(state['pos'][1], high[1] + 24),
                      (low[2] + high[2] + 1) / 2]
            if math.hypot(state['pos'][0] - center[0], state['pos'][2] - center[2]) > 48:
                self.travel_to_projection(client, center, projection_key, out)
            layout = self._layout(client, projection_key, out)
            ledger = self._ledger(client, layout)
            actual = ledger.actual
            gained, result = 0, None
            while gained < layout.config['max_cells_per_build']:
                state = self._safe_flat(client, layout)
                plan = next_batch(layout, actual, state, cell_budget=layout.config['max_cells_per_build'] - gained)
                write_json(out / 'flat-next-batch.json', plan)
                if plan['phase'] != 'ready':
                    result = {'phase': plan['phase'], 'detail': plan.get('detail', '当前图面方块已齐'),
                              'requirements': plan.get('requirements', {}), 'placed': gained}
                    break
                directory = out / ('window-%04d' % gained)
                after, count = self._window(client, layout, actual, plan, directory)
                journal = directory / 'flat-window.json'
                self.audit = ledger.accept(after, count, json.loads(journal.read_text()), evidence_path=journal)
                self.audit_dirty = False
                write_json(self.out / 'projection-latest.json', self.audit)
                gained += count
            return result or {'phase': 'done', 'detail': '本批地图画已确认，缺料清单已增量更新', 'placed': gained}

    def projection_loading_target(self, client, selection):
        low, high = selection['min'], selection['max']
        center=[(low[0]+high[0]+1)/2,0,(low[2]+high[2]+1)/2]
        here=client.status()['pos'];cruise=max(here[1],high[1]+24)
        remote=getattr(self,'profile',{}).get('remote_map_loading_cruise_y')
        if remote is not None:
            if type(remote)not in(int,float)or not math.isfinite(remote)or not high[1]+24<=remote<=250:
                raise JobBlocked('远资源区返图巡航高度登记无效，未移动')
            if math.hypot(center[0]-here[0],center[2]-here[2])>256:cruise=max(cruise,remote)
        center[1]=cruise
        return center

    def travel_to_projection(self, client, center, projection_key, out):
        """Return to the current selection through bounded existing Kit routes.

        Resource search authorization describes an ore destination, so it must
        not be fabricated for a flight back to the selected construction area.
        Each ordinary route below stays under the existing direct-route limit.
        """
        from material_jobs.acquisition import _travel, SEGMENT_ROUTE_LIMIT
        from material_jobs.navigation import lift_for_travel
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        trace = []
        try:
            lift_for_travel(client)
            for segment in range(16):
                self.checkpoint()
                state = client.status()
                if state.get('projection_selection', {}).get('key') != projection_key:
                    raise JobBlocked('返程期间投影选择已改变，保留当前航段')
                here = state['pos']
                gap = math.hypot(here[0] - center[0], here[2] - center[2])
                ratio = min(1., SEGMENT_ROUTE_LIMIT / gap) if gap else 1.
                target = [here[0] + (center[0]-here[0])*ratio,
                          max(here[1], center[1]),
                          here[2] + (center[2]-here[2])*ratio]
                trace.append({'event':'projection_return_segment', 'segment':segment+1,
                              'from':list(here), 'target':target, 'final_target':list(center)})
                write_json(out / 'model-loading-travel.json', trace)
                _travel(client, target, self.checkpoint, trace, keep_cruise=True)
                actual = client.status()
                if (actual.get('projection_selection', {}).get('key') != projection_key
                        or math.hypot(actual['pos'][0]-target[0], actual['pos'][2]-target[2]) > .75):
                    raise JobBlocked('原地图画返程航段未到达，不重放导航')
                if ratio == 1.:
                    return
            raise JobBlocked('地图画返程航段上限已到，保留当前位置')
        finally:
            write_json(out / 'model-loading-travel.json', trace)

    def recover(self, inflight):
        if inflight.get('operation') == 'build':
            for path in self.out.glob('*-build/window-*/flat-window.json'):
                record = json.loads(path.read_text())
                if record.get('pending') is not None or record.get('complete') is not True:
                    return {'phase': 'blocked', 'safe_to_replan': False,
                            'detail': '原地图画窗口仍需独立核对；保留它，不重新导航或放置'}
        return super().recover(inflight)

    def finish(self):
        pending = []
        for path in self.out.glob('*-build/window-*/flat-window.json'):
            record = json.loads(path.read_text())
            if record.get('pending') is None and record.get('complete') is True:
                continue
            if (record.get('pending')is None and record.get('no_effect_verified')is True
                    and record.get('placement_credit')==0
                    and type(record.get('inventory_before'))is int
                    and record['inventory_before']==record.get('inventory_after')):
                continue
            # A stopped preflight has consumed nothing. Its journal remains
            # unresolved, but it must not prevent ordinary healthy parking.
            if (record.get('pending') == 'navigate'
                    and not any((path.parent / name).exists() for name in
                                ('mask-receipt.json', 'native-receipt.json'))):
                continue
            pending.append(str(path))
        if pending:
            write_json(self.out / 'flat-unconfirmed-finish.json', {'pending_windows': pending,
                       'safe_to_replan': False, 'movement_or_mask_cleanup_sent': False})
            raise JobBlocked('地图画原窗口尚未核验；保留原生防护，不执行移动或清理')
        client = getattr(self, 'client', None)
        result = super().finish()
        if client is not None:
            try:
                from live_snapshot import read_fresh
                from projection_flat_continuity import save
                save(self, client, read_fresh(self.root))
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                pass  # Optional cache must never turn a confirmed park into a retry.
        return result


def create_backend(request, automation, out, checkpoint):
    return FlatMapBackend(request, automation, out, checkpoint)
