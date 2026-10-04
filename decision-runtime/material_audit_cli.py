"""Fresh selected-projection audit through Kit's read-only native interface.

This entry point creates no material lease, moves no player and sends no finish
or logout. The exact native receipt is retained even when validation fails.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from kit_runtime.journal import write_json
from material_client import Client
from material_jobs.protocol import server_key


DEFAULT_GAME = Path('/Applications/.minecraft/versions/26.1.2')


class AuditBlocked(RuntimeError):
    pass


def _selection(state):
    selected = state.get('projection_selection') or {}
    low, high = selected.get('min'), selected.get('max')
    if (not isinstance(selected.get('key'), str) or not selected['key']
            or not isinstance(low, list) or not isinstance(high, list)
            or len(low) != 3 or len(high) != 3
            or any(type(n) is not int for n in low + high)
            or any(a > b for a, b in zip(low, high))):
        raise AuditBlocked('请先选定完整投影；当前范围无法核验')
    return selected


def _ready(state):
    task = state.get('material_task') or {}
    printer = state.get('professional_printer') or {}
    if (state.get('connected') is not True or state.get('manual_movement')
            or state.get('screen') or task.get('process_alive') or task.get('occupied')
            or state.get('native_material_busy') or (state.get('build_job') or {}).get('active')
            or printer.get('enabled') or printer.get('owned')
            or (state.get('gravel') or {}).get('active')
            or (state.get('concrete') or {}).get('active')
            or any(state.get(k) for k in ('navigating', 'chopping', 'borer_active', 'printing',
                                         'planter_active', 'feeder_active', 'fisher_active'))):
        raise AuditBlocked('当前有游戏动作或人工接管；审计等待唯一控制者空闲')
    return _selection(state)


def _validate(receipt, before, after):
    selected = _selection(before)
    current = _selection(after)
    # projection_model/audit return a synchronous native snapshot containing
    # the complete result. Unlike scan/map_audit, that protocol does not add a
    # phase field. Never rewrite the original receipt to manufacture DONE.
    if (receipt.get('phase') not in (None, 'done')
            or receipt.get('world_session') != before.get('world_session')
            or any(before.get(k) != after.get(k) for k in
                   ('world_session', 'dimension', 'control_revision'))
            or server_key(before.get('server')) != server_key(after.get('server'))
            or any(selected[k] != current[k] for k in ('key', 'min', 'max'))):
        raise AuditBlocked('审计回执、世界或投影已变化；保留原回执，不重发')
    _ready(after)
    audit = receipt.get('projection_audit')
    if not isinstance(audit, dict):
        raise AuditBlocked('原生回执没有完整投影审计')
    observed = audit.get('observed_at')
    if (audit.get('audit_schema') != 2 or audit.get('loaded_chunks_verified') is not True
            or audit.get('placement_key') != selected['key']
            or audit.get('dimension') != before.get('dimension')
            or server_key(audit.get('server')) != server_key(before.get('server'))
            or type(observed) is not int or type(before.get('time')) is not int
            or type(after.get('time')) is not int
            or not before['time'] <= observed <= after['time']):
        raise AuditBlocked('投影范围、区块覆盖或审计时间尚未证明完整')
    matched, total = audit.get('matched'), audit.get('total')
    rows, kinds = audit.get('mismatches'), audit.get('kinds')
    if (type(matched) is not int or type(total) is not int or not 0 <= matched <= total
            or total < 1 or not isinstance(rows, list) or matched + len(rows) != total
            or not isinstance(kinds, dict)
            or any(k not in ('missing', 'occupied', 'state_only') or type(n) is not int or n < 0
                   for k, n in kinds.items())):
        raise AuditBlocked('投影审计数量或未加载格不可核验')
    seen, counted = set(), Counter()
    low, high = selected['min'], selected['max']
    for row in rows:
        pos = row.get('pos') if isinstance(row, dict) else None
        if (not isinstance(pos, list) or len(pos) != 3 or any(type(n) is not int for n in pos)
                or tuple(pos) in seen or any(not low[i] <= pos[i] <= high[i] for i in range(3))
                or row.get('kind') not in ('missing', 'occupied', 'state_only')):
            raise AuditBlocked('审计差格重复、越界或缺少完整分类')
        seen.add(tuple(pos)); counted[row['kind']] += 1
    if dict(counted) != {k: n for k, n in kinds.items() if n}:
        raise AuditBlocked('审计分类与实际差格数量不符')
    items = audit.get('replacement_items')
    if (not isinstance(items, dict) or any(not isinstance(k, str) or type(n) is not int or n <= 0
                                          for k, n in items.items())):
        raise AuditBlocked('审计材料差额格式无效')
    return audit


def _save_receipt(out, op, receipt):
    identity = receipt.get('id')
    if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', identity):
        raise AuditBlocked('原生回执没有可核验的请求编号')
    path = out / (op + '-receipt-' + identity + '.json')
    write_json(path, receipt)
    return path


def _model(receipt, selected, world):
    model = receipt.get('projection_model')
    if (receipt.get('phase') not in (None, 'done') or receipt.get('world_session') != world
            or not isinstance(model, dict) or model.get('model_schema') != 1
            or model.get('loaded_chunks_verified') is not True
            or model.get('placement_key') != selected['key']
            or model.get('bounds') != {'min': selected['min'], 'max': selected['max']}
            or type(model.get('observed_at')) is not int
            or not isinstance(model.get('expected'), list)
            or type(model.get('total')) is not int or model['total'] != len(model['expected'])):
        raise AuditBlocked('当前投影模型、世界或范围无法核验')
    expected, lines = {}, []
    for row in model['expected']:
        pos = row.get('pos') if isinstance(row, dict) else None
        if (not isinstance(pos, list) or len(pos) != 3 or any(type(n) is not int for n in pos)
                or tuple(pos) in expected
                or any(not selected['min'][i] <= pos[i] <= selected['max'][i] for i in range(3))
                or not isinstance(row.get('state'), str) or not isinstance(row.get('item'), str)):
            raise AuditBlocked('投影模型含重复、越界或无效目标格')
        expected[tuple(pos)] = row
        lines.append(','.join(map(str, pos)) + '\t' + row['state'] + '\t' + row['item'])
    digest = hashlib.sha256(''.join(line + '\n' for line in sorted(lines)).encode()).hexdigest()
    if digest != model.get('content_hash'):
        raise AuditBlocked('完整投影模型内容哈希不符')
    return model, expected


def _returned_read_result(client, receipt, op, before):
    """Bind a phase-less synchronous read to the exact returned request."""
    terminal = getattr(client, 'last_terminal_evidence', None) or {}
    rid = getattr(client, 'last', None)
    if (not isinstance(rid, str) or not rid or receipt.get('id') != rid
            or receipt.get('phase') not in (None, 'done')
            or receipt.get('world_session') != before.get('world_session')
            or type(receipt.get('control_revision')) is not int
            or receipt.get('control_revision') != before.get('control_revision')
            or terminal.get('request_id') != rid or terminal.get('op') != op
            or terminal.get('world_session') != before.get('world_session')
            or type(terminal.get('revision_after')) is not int
            or terminal.get('revision_after') != before.get('control_revision')
            or terminal.get('phase') != receipt.get('phase')):
        raise AuditBlocked('原生同步读取没有当前精确请求、世界和版本证明；保留原回执，不重发')


def _scan_boxes(low, high):
    """Cover the full envelope plus neighbor cells without exceeding native limits."""
    if any(a > b for a, b in zip(low, high)):
        raise AuditBlocked('投影扫描范围无效')
    sizes = [high[i] - low[i] + 1 for i in range(3)]
    if sizes[0] * sizes[1] * sizes[2] <= 50_000:
        yield low, high
        return
    axis = max(range(3), key=lambda i: sizes[i])
    middle = (low[axis] + high[axis]) // 2
    left, right = list(high), list(low)
    left[axis], right[axis] = middle, middle + 1
    yield from _scan_boxes(low, left)
    yield from _scan_boxes(right, high)


def _server_proof(client, out, before, selected, model, expected, audit):
    # hasChunk/hasChunkAt may include Bobby FakeChunk on older hosts. Native
    # scanCell already rejects those through LoadedServerChunkEvidence.
    low = [selected['min'][i] - 1 for i in range(3)]
    high = [selected['max'][i] + 1 for i in range(3)]
    low[1], high[1] = max(-64, low[1]), min(319, high[1])
    actual, paths, times = {}, [], []
    for part_low, part_high in _scan_boxes(low, high):
        receipt = client.request('scan', min=part_low, max=part_high, details=True, seconds=60)
        path = _save_receipt(out, 'server-scan', receipt); paths.append(str(path))
        write_json(path.with_suffix('.scope.json'), {'min': part_low, 'max': part_high, 'details': True})
        cells = 1
        for a, b in zip(part_low, part_high):
            cells *= b - a + 1
        if (receipt.get('phase') != 'done' or receipt.get('world_session') != before['world_session']
                or receipt.get('scan_cells_read') != cells or receipt.get('scan_total_cells') != cells
                or receipt.get('scan_start_revision') != before['control_revision']
                or receipt.get('scan_end_revision') != before['control_revision']
                or type(receipt.get('scan_started_at')) is not int
                or type(receipt.get('scan_ended_at')) is not int
                or not max(model['observed_at'], audit['observed_at']) <= receipt['scan_started_at'] <= receipt['scan_ended_at']
                or not isinstance(receipt.get('blocks'), list)):
            raise AuditBlocked('真实服务器区块扫描未完整结束；保留回执，不使用缓存差额')
        times.append((receipt['scan_started_at'], receipt['scan_ended_at']))
        for row in receipt['blocks']:
            pos = row.get('pos') if isinstance(row, dict) else None
            if (not isinstance(pos, list) or len(pos) != 3 or any(type(n) is not int for n in pos)
                    or tuple(pos) in actual
                    or any(not part_low[i] <= pos[i] <= part_high[i] for i in range(3))
                    or not isinstance(row.get('state'), str)
                    or any(type(row.get(k)) is not bool for k in ('fluid', 'block_entity', 'replaceable'))):
                raise AuditBlocked('真实扫描含重复、越界或缺少属性的格子')
            actual[tuple(pos)] = row
    rows, kinds, items, mismatch_blocks = [], Counter(), Counter(), Counter()
    matched = 0
    for pos, target in expected.items():
        observed = actual.get(pos, {})
        state = observed.get('state', 'Block{minecraft:air}')
        if state == target['state']:
            matched += 1
            continue
        wanted_block = target['state'].split('}', 1)[0]
        actual_block = state.split('}', 1)[0]
        kind = 'state_only' if wanted_block == actual_block else 'missing' if observed.get('replaceable', True) else 'occupied'
        neighbors = [(pos[0]+dx, pos[1]+dy, pos[2]+dz)
                     for dx, dy, dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))]
        neighbor_coverage = all(low[1] <= p[1] <= high[1] for p in neighbors)
        rows.append({'pos': list(pos), 'expected': target['state'], 'actual': state, 'kind': kind,
                     'fluid': observed.get('fluid', False), 'block_entity': observed.get('block_entity', False),
                     'neighbors_loaded': neighbor_coverage,
                     'adjacent_fluid': any(actual.get(p, {}).get('fluid', False) for p in neighbors)})
        kinds[kind] += 1; mismatch_blocks[actual_block.removeprefix('Block{')] += 1
        if (kind != 'state_only' and target['item'] != 'minecraft:air'
                and 'half=upper' not in target['state'] and 'part=head' not in target['state']):
            items[target['item']] += 1
    identity = lambda row: (tuple(row['pos']), row['expected'], row['actual'], row['kind'])
    if (matched != audit['matched'] or len(expected) != audit['total']
            or dict(kinds) != {k: n for k, n in audit['kinds'].items() if n}
            or dict(items) != audit['replacement_items']
            or {identity(r) for r in rows} != {identity(r) for r in audit['mismatches']}):
        raise AuditBlocked('原生投影缓存审计与真实服务器方块不一致；保留全部证据，重新加载后核验')
    end = max(t[1] for t in times)
    client.minimum_status_time = max(end, getattr(client, 'minimum_status_time', 0) or 0)
    return {**audit, 'observed_at': end, 'native_projection_audit_observed_at': audit['observed_at'],
            'mismatches': rows, 'kinds': dict(kinds), 'replacement_items': dict(items),
            'actual_mismatch_blocks': dict(mismatch_blocks), 'loaded_server_chunks_verified': True,
            'observation_source': 'native_scan_loaded_server_chunks',
            'source_model_content_hash': model['content_hash'], 'server_scan_receipts': paths,
            'server_scan_started_at': min(t[0] for t in times), 'server_scan_ended_at': end,
            'server_scan_scope': 'complete_selected_envelope_and_neighbors_sampled_on_client_ticks_not_atomic_snapshot',
            'auxiliary_audit_scope': 'native_decorations_and_enclosed_air_not_recomputed_by_server_scan'}


def run(automation, out, *, client_factory=Client):
    automation, out = Path(automation), Path(out)
    # Read the live server through the same client freshness/interlock boundary;
    # only the constructor's server assertion needs this initial local snapshot.
    from live_snapshot import read_fresh
    state = read_fresh(automation)
    _ready(state)
    client = client_factory(automation, out, server=state['server'])
    before = client.status()
    selected = _ready(before)
    model_receipt = client.request('projection_model')
    model_path = _save_receipt(out, 'projection-model', model_receipt)
    _returned_read_result(client, model_receipt, 'projection_model', before)
    model, expected = _model(model_receipt, selected, before['world_session'])
    receipt = client.request('projection_audit')
    receipt_path = _save_receipt(out, 'projection-audit', receipt)
    _returned_read_result(client, receipt, 'projection_audit', before)
    # Native scan time can be a few milliseconds newer than its outer snapshot.
    # Wait for the already published status; never issue another audit request.
    projection = receipt.get('projection_audit')
    observed = projection.get('observed_at') if isinstance(projection, dict) else None
    if type(observed) is int:
        client.minimum_status_time = max(observed, getattr(client, 'minimum_status_time', 0) or 0)
    after = client.status()
    audit = _validate(receipt, before, after)
    if not before['time'] <= model['observed_at'] <= audit['observed_at']:
        raise AuditBlocked('投影模型观察时间不属于本次审计')
    audit = _server_proof(client, out, before, selected, model, expected, audit)
    after = client.status()
    _validate({**receipt, 'projection_audit': audit}, before, after)
    audit_path, inventory_path = out / 'current-projection.json', out / 'world-inventory.json'
    write_json(audit_path, audit)
    write_json(inventory_path, {key: after.get(key) for key in
               ('time', 'world_session', 'server', 'dimension', 'health', 'food', 'pos',
                'projection_selection', 'inventory', 'supervision_lease', 'flight',
                'guard_armed', 'guard_pve_only', 'manual_movement')})
    return {'schema': 1, 'phase': 'done', 'read_only': True,
            'world_session': after['world_session'], 'observed_at': audit['observed_at'],
            'matched': audit['matched'], 'total': audit['total'],
            'remaining': audit['total'] - audit['matched'], 'kinds': audit['kinds'],
            'remaining_materials': len(audit['replacement_items']),
            'loaded_chunks_verified': True, 'loaded_server_chunks_verified': True,
            'model_content_hash': model['content_hash'], 'audit_path': str(audit_path),
            'inventory_path': str(inventory_path), 'receipt_path': str(receipt_path),
            'model_receipt_path': str(model_path), 'server_scan_receipts': audit['server_scan_receipts']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, default=DEFAULT_GAME)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args.game_dir / 'config/twob2tkit/automation', args.out)
        print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, AssertionError) as error:
        print(json.dumps({'schema': 1, 'phase': 'waiting', 'read_only': True,
                          'detail': str(error), 'automatic_retry_allowed': False},
                         ensure_ascii=False, separators=(',', ':')))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
