"""Read-only review of a registered unresolved cycle; never grants replay permission."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from farm_caretaker import STAGES, validate_profile
from material_jobs.protocol import server_key


def _read(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 262144:
        raise ValueError('原周期记录不存在或过大：' + str(path))
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('原周期记录格式无效：' + str(path))
    return value


def inspect_pending(automation, profile, out=None, *, now_ms=None):
    """Read files only, including status.json; no client, mailbox, lease or journal writes."""
    root, profile = Path(automation), validate_profile(profile)
    key = hashlib.sha256((profile['server'] + '|' + profile['dimension']).encode()).hexdigest()[:20]
    home = root / 'farm-caretakers' / key
    registry = _read(home / 'registry.json')
    directory = Path(registry['directory']).resolve()
    if registry.get('profile') != profile or (out is not None and Path(out).resolve() != directory):
        raise ValueError('农场登记配置或原记录目录已改变；不采用其它周期记录')
    book = _read(directory / 'caretaker.json')
    if book.get('profile') != profile or book.get('schema') != 1:
        raise ValueError('原周期记录与登记配置不一致')
    result = {'phase': 'waiting', 'code': 'WAIT_RECONCILE', 'can_resume': False,
              'ai_calls': 0, 'writes_performed': False, 'journal': str(directory / 'caretaker.json'),
              'original_pending': deepcopy(book.get('pending')), 'checks': [], 'manual_checks': []}
    if not book.get('pending'):
        result.update(phase='idle', code='NO_PENDING', detail='原周期没有未确认动作；开始或恢复仍须重新核对安全状态。')
        return result
    cycle, pending = book.get('current_cycle'), book['pending']
    if (not isinstance(cycle, dict) or type(cycle.get('id')) is not int or cycle['id'] < 1
            or not isinstance(pending, dict) or pending.get('stage') not in STAGES):
        raise ValueError('原未确认周期结构无效；不能采用其它路径')
    expected = directory / ('cycle-%06d' % cycle['id'])
    stage_dir = expected / pending['stage']
    if (Path(cycle.get('directory', '')).resolve() != expected
            or Path(pending.get('directory', '')).resolve() != stage_dir
            or not stage_dir.resolve().is_relative_to(directory)):
        raise ValueError('原未确认动作目录不属于同一周期；拒绝读取外部记录')
    stage_path = stage_dir / 'stage.json'
    stage = _read(stage_path)
    if (stage.get('cycle_id') != cycle['id'] or stage.get('stage') != pending['stage']
            or stage.get('world_session') != cycle.get('world_session')):
        raise ValueError('原阶段与周期世界不一致')
    intent = stage.get('pending')
    result.update(cycle_id=cycle['id'], stage=pending['stage'], stage_journal=str(stage_path),
                  world_session=cycle.get('world_session'), original_intent=deepcopy(intent))
    if not isinstance(intent, dict):
        result['checks'].append({'code': 'MISSING_STAGE_INTENT', 'detail': '协调器仍有未确认阶段，但没有可用的原动作记录。'})
    else:
        operation = intent.get('operation')
        result.update(operation=operation, params=deepcopy(intent.get('params', {})))
        baseline = intent.get('before_counts')
        if not isinstance(baseline, dict):
            result['checks'].append({'code': 'MISSING_ACTION_BASELINE', 'detail': '缺少该动作开始前的库存；周期最初库存不能替代取料前库存。'})
        else:
            result['inventory_before'] = deepcopy(baseline)
        # A parent fetch intent can contain navigation, opening, clicks and transfers.
        # Missing completed events cannot prove that those children never dispatched.
        result['checks'].append({'code': 'UNCONFIRMED_CHILD_DISPATCH', 'detail': '缺少与原动作绑定的完整发送链和最终回执；导航停止或防护停车不能证明取料已完成或从未发送。'})
        if operation == 'fetch':
            result['manual_checks'].append('核对取料前背包、当前背包和光标，以及原登记箱里的种薯；目标数量表示所需背包总量，不是已取出数量。')
            result['manual_checks'].append('核对是否开箱、取料或点击过物品；不能仅凭日志没有开箱事件就清除取料记录。')
        else:
            result['manual_checks'].append('按原动作和内部记录核对物品、目标方块或动物的实际变化；未知动作不能清除或重放。')
        inner = intent.get('inner_journal')
        if inner:
            result['inner_journal'] = inner
    now = int(time.time() * 1000) if now_ms is None else now_ms
    try:
        current = _read(root / 'status.json')
        result['current_world_session'] = current.get('world_session')
        if (current.get('connected') is not True or server_key(current.get('server')) != profile['server']
                or current.get('dimension') != profile['dimension']
                or current.get('world_session') != cycle.get('world_session')):
            result['checks'].append({'code': 'WORLD_SCOPE_CHANGED', 'detail': '当前世界会话与原周期不同；不能在新会话采用或重放原动作。'})
        if type(current.get('time')) is not int or not -2000 <= now - current['time'] <= 2500:
            result['checks'].append({'code': 'STALE_CURRENT_STATE', 'detail': '当前状态不是新鲜观察；不能用于库存或世界核对。'})
        else:
            from material_plan import inventory_counts
            counts = dict(inventory_counts(current))
            result['current_inventory'] = counts
            if isinstance(intent, dict) and isinstance(intent.get('before_counts'), dict) and counts != intent['before_counts']:
                result['checks'].append({'code': 'INVENTORY_CHANGED', 'detail': '当前库存与该动作开始前不同；数量变化不能自动归因于原取料动作。'})
    except (ValueError, OSError, TypeError, KeyError) as error:
        result['checks'].append({'code': 'CURRENT_STATE_UNAVAILABLE', 'detail': '当前只读状态无法核对：' + str(error)})
    result['manual_checks'].append('核对原阶段记录和对应后台的 events、箱子来源及原生精确回执；保留原 pending 历史。')
    result['detail'] = '原动作仍未确认，检查没有执行游戏动作或改写记录；不能安全恢复。'
    return result
