"""Opt-in flat-map construction adapter for the existing material scheduler.

No new action controller, configuration change or automatic job launch. Supply,
recipes, processing, control and parking stay with the existing Backend. Every
window retains its journal until native ACK, physical cells and stock agree.
"""
import json
import math
from pathlib import Path
import time

from kit_runtime.journal import write_json
from material_jobs.protocol import JobBlocked
from material_jobs_backend import Backend
from material_plan import inventory_counts
from projection_flat_plan import FlatLayout, next_batch, policy, position
from projection_patch_plan import connected_mask
from projection_scene_lights import registered_map_light


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
    for p, row in observed.items():
        if p[1] != layout.low[1]:
            if registered_map_light(row, layout.expected, observed, layout.config['registered_lights'], layout.low[1]):
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
    def __init__(self, request, automation, out, checkpoint):
        if request.get('mode') != 'projection':
            raise ValueError('Flat-map adapter requires an explicit projection task')
        policy(request.get('flat_map'))  # Validate before constructing the existing backend.
        super().__init__(request, automation, out, checkpoint)

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
        self._safe_flat(client, layout)
        if client.status().get('projection_batch', {}).get('active'):
            raise JobBlocked('既有施工掩码尚未清除；不覆盖它')
        directory.mkdir()
        journal = {'schema': 1, 'world_session': client.world, 'task_session': client.task,
                   'placement_key': layout.key, 'plan': plan, 'complete': False, 'pending': 'navigate'}
        save = lambda: write_json(directory / 'flat-window.json', journal)
        save()
        trace = []
        _travel(client, plan['station'], self.checkpoint, trace, keep_cruise=False)
        write_json(directory / 'travel.json', trace)
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
                       inventory_before=stock_before, inventory_after=stock_before - len(changed))
        save()
        return after, len(changed)

    def build(self, projection_key):
        with self.action('build') as (client, out):
            self.prepare_travel()
            model_reply = client.request('projection_model')
            write_json(out / 'flat-model.json', model_reply)
            if model_reply.get('world_session') != client.world:
                raise JobBlocked('地图画模型不属于当前世界')
            layout = FlatLayout(model_reply.get('projection_model'), self.request['flat_map'])
            if layout.key != projection_key:
                raise JobBlocked('地图画目标投影已改变')
            audit = self.refresh_audit()
            actual = layout.observed(audit)
            gained, result = 0, None
            while gained < layout.config['max_cells_per_build']:
                state = self._safe_flat(client, layout)
                plan = next_batch(layout, actual, state, cell_budget=layout.config['max_cells_per_build'] - gained)
                write_json(out / 'flat-next-batch.json', plan)
                if plan['phase'] != 'ready':
                    result = {'phase': plan['phase'], 'detail': plan.get('detail', '当前图面方块已齐'),
                              'requirements': plan.get('requirements', {}), 'placed': gained}
                    break
                after, count = self._window(client, layout, actual, plan, out / ('window-%04d' % gained))
                actual.update(after)
                gained += count
            final = self.refresh_audit()
            final_actual = layout.observed(final)
            if any(final_actual.get(p) != v for p, v in actual.items()) or final['matched'] - audit['matched'] != gained:
                raise JobBlocked('窗口结果与完整实机审计不一致；保留全部原记录')
            return result or {'phase': 'done', 'detail': '本批地图画通过原生、物资和完整图面复核', 'placed': gained}

    def recover(self, inflight):
        if inflight.get('operation') == 'build':
            for path in self.out.glob('*-build/window-*/flat-window.json'):
                record = json.loads(path.read_text())
                if record.get('pending') is not None or record.get('complete') is not True:
                    return {'phase': 'blocked', 'safe_to_replan': False,
                            'detail': '原地图画窗口仍需独立核对；保留它，不重新导航或放置'}
        return super().recover(inflight)

    def finish(self):
        pending = [str(path) for path in self.out.glob('*-build/window-*/flat-window.json')
                   if (record := json.loads(path.read_text())).get('pending') is not None
                   or record.get('complete') is not True]
        if pending:
            write_json(self.out / 'flat-unconfirmed-finish.json', {'pending_windows': pending,
                       'safe_to_replan': False, 'movement_or_mask_cleanup_sent': False})
            raise JobBlocked('地图画原窗口尚未核验；保留原生防护，不执行移动或清理')
        return super().finish()


def create_backend(request, automation, out, checkpoint):
    return FlatMapBackend(request, automation, out, checkpoint)
