"""Bounded stockpile batches over the existing, already owned material backend.

``target_count`` is the finished quantity in the approved depots, not a carried
inventory target. Pass an existing Backend, or its MaterialClient with
``client.mineral_backend = backend``. This module never creates a controller,
changes a profile on disk, predicts stock from cache, or implements navigation.
"""
import json
from pathlib import Path
import time

from kit_runtime.journal import write_json
from material_depots import audit, exchange
from material_plan import inventory_counts
from .acquisition import ROCK_SOURCES
from .planning import plan
from .protocol import JobBlocked, JobPaused


ITEMS = frozenset('minecraft:' + name for name in (
    'raw_iron_block', 'diorite', 'tuff', 'stone', 'deepslate', 'lodestone'))
IRON, RAW = 'minecraft:raw_iron_block', 'minecraft:raw_iron'
HOLD_CODES = frozenset(('guard_displaced', 'route_geometry_blocked', 'route_uncertain'))


class _Wait(Exception):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail


def _bound_backend(client):
    if callable(getattr(client, 'ensure_client', None)):
        backend, native = client, getattr(client, 'client', None)
    else:
        backend = getattr(client, 'mineral_backend', None) or getattr(client, 'material_backend', None)
        native = client
    if backend is None or native is None or getattr(backend, 'client', None) is not native:
        raise JobBlocked('矿物流水线需要绑定同一个已有材料后端和客户端，不能创建第二控制者')
    return backend, native


def _snapshot(c, world, checkpoint):
    checkpoint()
    state = c.status()  # Existing client checks its current revision/lease.
    if not state.get('connected') or state.get('world_session') != world:
        raise JobPaused('矿物流水线世界已经变化，保留批次记录')
    if state.get('manual_movement'):
        raise JobPaused('玩家正在接管，矿物流水线保持暂停')
    rows = [r for r in state.get('inventory', []) if 0 <= r.get('slot', -1) < 36]
    if len(rows) != 36 or len({r['slot'] for r in rows}) != 36:
        raise JobBlocked('矿物流水线需要完整的36格现物背包')
    if any(state.get(k) for k in ('borer_active', 'chopping', 'navigating', 'native_material_busy')):
        raise JobPaused('原生工作仍在运行；矿物流水线没有提交下一动作')
    return state


def run(c, profile, item, target_count, out, checkpoint):
    """Produce/store finite batches; known waits resume from the same journal.

    Backend.acquire already prepares tools, resolves held routes and invokes
    persistent live discovery/native quarry. Backend.craft/smelt retain their
    existing door, shaft, menu and furnace recovery. Unexpected exceptions keep
    the outer ``pending`` marker: the owner must reconcile that exact backend
    action/transfer before running again; inventory alone never clears it.
    """
    if item not in ITEMS or type(target_count) is not int or not 1 <= target_count <= 1_000_000:
        raise ValueError('Unsupported mineral item or finished target')
    backend, client = _bound_backend(c)
    if profile != backend.profile:
        raise JobBlocked('矿物流水线工位必须与当前已核验后端一致')
    depots = profile.get('depots', [])
    if not depots or len({tuple(p) for p in depots}) != len(depots):
        raise JobBlocked('矿物流水线需要不同的已登记仓库；不能由缓存坐标生成仓库')
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    path = out / 'mineral-pipeline.json'
    world = client.world
    current = _snapshot(client, world, checkpoint)
    scope = {k: current.get(k) for k in ('server', 'dimension', 'world_session')}
    limits = profile.get('mineral_pipeline_max_actions', 256)
    if type(limits) is not int or not 1 <= limits <= 4096:
        raise ValueError('mineral_pipeline_max_actions must be 1..4096')
    seconds = profile.get('mineral_pipeline_max_seconds', 7200)
    if type(seconds) is not int or not 1 <= seconds <= 86400:
        raise ValueError('mineral_pipeline_max_seconds must be 1..86400')
    started = time.monotonic()
    if path.exists():
        if path.stat().st_size > 1_000_000:
            raise JobBlocked('矿物批次账本过大，保留现场')
        try:
            journal = json.loads(path.read_text())
        except (OSError, ValueError) as error:
            raise JobBlocked('矿物批次账本无法解析，保留现场') from error
        if not isinstance(journal, dict):
            raise JobBlocked('矿物批次账本需要JSON对象，未移动或重新生产')
        if (journal.get('schema') != 1 or journal.get('scope') != scope
                or journal.get('item') != item or journal.get('target') != target_count
                or journal.get('depots') != depots):
            raise JobPaused('矿物流水线账本范围或目标已变化，不能沿用旧记录')
        batch = journal.get('batch')
        expected = journal.get('expected_depot')
        if (expected is not None and (type(expected) is not int or expected < 0)
                or type(journal.get('deposited')) is not int or journal['deposited'] < 0
                or not isinstance(journal.get('receipts'), list)
                or batch is not None and (not isinstance(batch, dict)
                    or type(batch.get('amount')) is not int or not 1 <= batch['amount'] <= 128
                    or batch.get('stage') not in ('produce', 'deposit'))):
            raise JobBlocked('矿物批次账本格式不符，未移动或重新生产')
        if journal.get('pending'):
            return {'phase': 'waiting', 'code': 'WAIT_RECEIPT', 'detail': '旧动作结果尚未核对；不重放',
                    'journal': str(path), 'pending': journal['pending'], 'ai_calls': 0}
    else:
        journal = {'schema': 1, 'scope': scope, 'item': item, 'target': target_count,
                   'depots': depots, 'expected_depot': None, 'deposited': 0,
                   'batch': None, 'pending': None, 'receipts': []}
        write_json(path, journal)
    actions = 0
    keep_inputs = {item, RAW}

    def fresh():
        return _snapshot(client, world, checkpoint)

    def stock():
        return dict(inventory_counts(fresh()))

    def invoke(kind, fn, args=()):
        nonlocal actions
        if actions >= limits or time.monotonic() - started >= seconds:
            raise _Wait('WAIT_BUDGET', '本轮动作或时间上限已到，已确认批次可继续')
        before = fresh()
        journal['pending'] = {'kind': kind, 'args': list(args),
                              'inventory_before': dict(inventory_counts(before)),
                              'request_before': getattr(client, 'last', None)}
        write_json(path, journal); actions += 1
        result = fn()
        after = fresh()
        if result is not None and not isinstance(result, dict):
            raise JobBlocked('材料后端回执格式未知，保留在途记录')
        if (kind in ('fetch', 'acquire', 'craft', 'smelt', 'make_room')
                and (result or {}).get('phase') not in ('done', 'waiting', 'blocked', 'paused', 'error')):
            raise JobBlocked('材料后端动作状态未知，保留在途记录')
        journal['receipts'].append({'kind': kind, 'request_id': getattr(client, 'last', None),
                                    'phase': (result or {}).get('phase'),
                                    'code': (result or {}).get('code'),
                                    'inventory_after': dict(inventory_counts(after))})
        journal['receipts'] = journal['receipts'][-32:]
        journal['pending'] = None; write_json(path, journal)
        return result or {'phase': 'done'}

    def check_reply(reply, default='WAIT_SOURCE'):
        code = reply.get('code')
        if code in HOLD_CODES or reply.get('phase') in ('blocked', 'paused', 'error'):
            raise _Wait(code or default, reply.get('detail', '现有接口等待前置核验'))

    def fetch(item_id, desired):
        if stock().get(item_id, 0) >= desired:
            return
        reply = invoke('fetch', lambda: backend.fetch({item_id: desired}), [{item_id: desired}])
        check_reply(reply)
        if stock().get(item_id, 0) < desired and callable(getattr(backend, 'fetch_packed', None)):
            reply = invoke('fetch_packed', lambda: backend.fetch_packed({item_id: desired}),
                           [{item_id: desired}])
            check_reply(reply)

    def supply(item_id, desired):
        # Finished depot stock already counts toward the order. Withdrawing it
        # as the next batch would invalidate the ledger and manufacture nothing.
        if item_id != item:
            fetch(item_id, desired)
        while stock().get(item_id, 0) < desired:
            if item_id not in ROCK_SOURCES:
                raise _Wait('WAIT_SOURCE', '现有接口没有该原料采集适配器：' + item_id)
            before = stock().get(item_id, 0)
            reply = invoke('acquire', lambda: backend.acquire(item_id, desired), [item_id, desired])
            if reply.get('code') == 'quarry_backpack_reserve':
                # This code is returned only after the existing adapter proves
                # the stopped request and remaining geometry. Its make_room
                # protects baseline stock, gear and these recipe inputs.
                state = fresh()
                free_before = sum(not row['count'] for row in state['inventory'] if row['slot'] < 36)
                room = invoke('make_room', lambda: backend.make_room(
                    {item_id: desired}, sorted(keep_inputs | {item_id})),
                    [{item_id: desired}, sorted(keep_inputs | {item_id})])
                check_reply(room, 'WAIT_CAPACITY')
                free_after = sum(not row['count'] for row in fresh()['inventory'] if row['slot'] < 36)
                if free_after <= free_before:
                    raise _Wait('WAIT_CAPACITY', '副产物寄存后没有核对到新空槽；不重启采坑')
                continue
            check_reply(reply)
            after = stock().get(item_id, 0)
            if after <= before:
                progress = reply.get('search_progress') or {}
                # The existing discovery ledger can make real bounded progress
                # without inventory; do not loop an unchanged failed source.
                if progress.get('has_more') and any(progress.get(k, 0) > 0 for k in
                                                   ('new_tiles', 'coarse_new_cells', 'seed_processed', 'bobby_checked')):
                    continue
                raise _Wait('WAIT_SOURCE', reply.get('detail', '未核对到可采矿点或实际物品增量'))

    def produce(desired):
        if item == IRON:
            needed = max(0, desired - stock().get(IRON, 0))
            if needed:
                supply(RAW, needed * 9)
                before = stock()
                reply = invoke('craft', lambda: backend.craft({IRON: desired}), [{IRON: desired}])
                check_reply(reply, 'WAIT_CRAFT')
                after = stock(); made = after.get(IRON, 0) - before.get(IRON, 0)
                if made <= 0 or before.get(RAW, 0) - after.get(RAW, 0) != made * 9:
                    journal['pending'] = {'kind': 'craft_verification',
                                          'inventory_before': before, 'inventory_after': after}
                    write_json(path, journal)
                    raise JobBlocked('粗铁压缩现物不满足九比一守恒；保留回执，不能再次合成')
            return
        while stock().get(item, 0) < desired:
            if item in ROCK_SOURCES:
                supply(item, desired)
                continue
            recipe_plan = plan(backend.catalog, {item: desired}, stock(), backend.warehouse_hint)
            steps = [step for step in recipe_plan['steps'] if step['kind'] != 'reserve']
            keep_inputs.update(ingredient for step in steps for ingredient in step.get('ingredients', {}))
            final = next((step for step in reversed(steps) if step.get('item') == item), None)
            # Fetch finished ingredients (notably owned iron ingots for lodestone)
            # before collecting a planner's lower-level raw-metal prerequisite.
            if final:
                for ingredient, amount in final.get('ingredients', {}).items():
                    fetch(ingredient, amount)
            recipe_plan = plan(backend.catalog, {item: desired}, stock(), backend.warehouse_hint)
            step = next((s for s in recipe_plan['steps'] if s['kind'] != 'reserve'), None)
            if step is None:
                raise _Wait('WAIT_RECIPE', '现物尚未达到目标，配方没有可执行动作')
            if step['kind'] == 'acquire':
                supply(step['item'], stock().get(step['item'], 0) + step['count'])
            elif step['kind'] == 'smelt':
                output_target = stock().get(step['item'], 0) + step['produced']
                reply = invoke('smelt', lambda: backend.smelt(step, output_target), [step, output_target])
                check_reply(reply, 'WAIT_FURNACE')
                for ingredient, amount in reply.get('requirements', {}).items():
                    supply(ingredient, amount)
                if reply.get('phase') != 'done' and not reply.get('requirements'):
                    raise _Wait('WAIT_FURNACE', reply.get('detail', '熔炉现物尚未确认'))
            elif step['kind'] == 'craft':
                output_target = stock().get(step['item'], 0) + step['produced']
                before = stock()
                reply = invoke('craft', lambda: backend.craft({step['item']: output_target}),
                               [{step['item']: output_target}])
                check_reply(reply, 'WAIT_CRAFT')
                if stock().get(step['item'], 0) <= before.get(step['item'], 0):
                    raise _Wait('WAIT_CRAFT', '合成没有实际现物增量')
            else:
                raise _Wait('WAIT_RECIPE', '矿物流水线不支持配方动作：' + step['kind'])

    def depot_count():
        result = invoke('depot_audit', lambda: audit(client, depots, [item]))
        if result.get('complete') is not True or result.get('world_session') != world:
            raise JobBlocked('仓库审计没有完整同世界回执')
        amount = result.get('counts', {}).get(item)
        if type(amount) is not int or amount < 0:
            raise JobBlocked('仓库审计数量未知')
        return amount

    try:
        invoke('prepare_travel', backend.prepare_travel)
        # The existing backend stages a safe dry return from a distant mine.
        invoke('stage_near_base', lambda: backend.stage_near_base(depots))
        actual = depot_count()
        if journal['expected_depot'] is None:
            journal['expected_depot'] = actual; write_json(path, journal)
        elif actual != journal['expected_depot']:
            raise _Wait('WAIT_STOCK_CHANGED', '仓库数量与已核对账本不符，先核对外部取放')
        while journal['expected_depot'] < target_count:
            if journal['batch'] is None:
                amount = min(64 if item == IRON else 128, target_count - journal['expected_depot'])
                journal['batch'] = {'amount': amount, 'stage': 'produce'}; write_json(path, journal)
            batch = journal['batch']
            if batch['stage'] == 'produce':
                produce(batch['amount'])
                if stock().get(item, 0) < batch['amount']:
                    raise _Wait('WAIT_SOURCE', '背包实际成品尚未达到本批入库量')
                batch['stage'] = 'deposit'; write_json(path, journal)
            invoke('prepare_travel', backend.prepare_travel)
            invoke('stage_near_base', lambda: backend.stage_near_base(depots))
            before_depot = depot_count()
            if before_depot != journal['expected_depot']:
                raise _Wait('WAIT_STOCK_CHANGED', '寄存前仓库数量已变化，不能累计旧账本')
            before = stock().get(item, 0)
            keep = before - batch['amount']
            if keep < 0:
                raise _Wait('WAIT_STOCK_CHANGED', '已生产成品离开了背包，停止寄存')
            reply = invoke('deposit', lambda: exchange(client, depots, deposit={item: keep}),
                           [{'deposit': {item: keep}}])
            after = stock().get(item, 0)
            # Keep an in-flight reconciliation marker while the post-transfer
            # audit runs. A crash here must not quietly repeat the exchange.
            journal['pending'] = {'kind': 'deposit_verification', 'before_depot': before_depot,
                                  'before_carried': before, 'after_carried': after,
                                  'keep': keep, 'reply': reply}
            write_json(path, journal)
            observed = audit(client, depots, [item])
            carried_after_audit = stock().get(item, 0)
            gained = before - after
            if (observed.get('complete') is not True or observed.get('world_session') != world
                    or observed.get('counts', {}).get(item) != before_depot + gained
                    or carried_after_audit != after
                    or not 0 <= gained <= batch['amount']):
                raise JobBlocked('寄存没有得到菜单与背包的实际守恒核验；不能重放')
            if reply.get('complete') is True and (reply.get('remaining_deposit') or after != keep):
                raise JobBlocked('寄存完成回执与实际背包不符；不能累计')
            journal['pending'] = None
            journal['deposited'] += gained; journal['expected_depot'] += gained
            batch['amount'] -= gained
            journal['raw_remainder'] = stock().get(RAW, 0)
            if not batch['amount']:
                journal['batch'] = None
            write_json(path, journal)
            if reply.get('complete') is not True or not gained:
                raise _Wait('WAIT_DEPOT', '仓库容量不足或寄存只完成一部分；已确认增量保留')
        journal['completed'] = True; write_json(path, journal)
        return {'phase': 'done', 'item': item, 'target': target_count,
                'verified_depot_count': journal['expected_depot'], 'deposited': journal['deposited'],
                'journal': str(path), 'ai_calls': 0}
    except _Wait as stopped:
        return {'phase': 'waiting', 'code': stopped.code, 'detail': stopped.detail,
                'verified_depot_count': journal['expected_depot'], 'deposited': journal['deposited'],
                'journal': str(path), 'ai_calls': 0}
