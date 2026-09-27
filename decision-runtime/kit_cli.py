"""Compact local command line for Kit's existing client-tick request interface.

Commands are requests to the running mod, not keyboard or mouse automation.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


DEFAULT_GAME = Path('/Applications/.minecraft/versions/26.1.2')


class KitControlError(RuntimeError):
    pass


def read_json(path):
    return json.loads(path.read_text())


def live_status(root):
    path = root / 'status.json'
    state = read_json(path)
    if time.time() * 1000 - state.get('time', 0) > 3000:
        raise KitControlError('游戏状态已过期，先确认 Minecraft 正在运行')
    return state


def compact(root, state):
    config_path = root.parent.parent / 'twob2tkit.json'
    config = read_json(config_path) if config_path.exists() else {}
    gravel = state.get('gravel') or {}
    return {
        'kit_version': state.get('kit_version'),
        'connected': state.get('connected'),
        'server': state.get('server'),
        'health': state.get('health'),
        'air': state.get('air_supply'),
        'oxygen_bonus': state.get('oxygen_bonus'),
        'air_expected_seconds': state.get('air_expected_seconds'),
        'air_return_floor': state.get('air_return_floor'),
        'air_budget_source': state.get('air_budget_source'),
        'radius': config.get('gravelRadius'),
        'depth': config.get('gravelDepth'),
        'limit': config.get('gravelLimit'),
        'active': gravel.get('active'),
        'collected': gravel.get('collected'),
        'phase': gravel.get('phase'),
        'status': gravel.get('status'),
    }


def make_request(state, op, radius=None, depth=None, limit=None):
    if not state.get('connected') or not state.get('world_session'):
        raise KitControlError('角色当前未进入世界')
    if state.get('manual_movement') and op != 'gravel_stop':
        raise KitControlError('玩家正在手动移动，命令已让出控制')
    request = {
        'id': 'kitcli-' + uuid.uuid4().hex[:16],
        'op': op,
        'server': state['server'],
        'dimension': state['dimension'],
        'site': state['pos'],
        'world_session': state['world_session'],
        'expected_revision': state['control_revision'],
        'expires_at': int(time.time() * 1000) + 5000,
    }
    for name, value in (('radius', radius), ('depth', depth), ('limit', limit)):
        if value is not None:
            request[name] = value
    return request


def send(root, request, timeout=8):
    path = root / 'request.json'
    state = live_status(root)
    if request.get('op')!='gravel_stop':
        from safety_interlock import require_unlocked
        require_unlocked(root,state)
    if path.exists() and read_json(path).get('id') != state.get('last_request'):
        raise KitControlError('已有尚未确认的命令；不会覆盖或重复发送')
    fd, temporary = tempfile.mkstemp(prefix='.kitcli-', suffix='.json', dir=root)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(request, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    deadline = time.monotonic() + timeout
    reply = root / ('reply-' + request['id'] + '.json')
    while time.monotonic() < deadline:
        state = live_status(root)
        result = read_json(reply) if reply.exists() else state
        if result.get('id') == request['id'] and result.get('phase') in ('done', 'error', 'stopped', 'waiting'):
            if result['phase'] != 'done':
                raise KitControlError(result.get('detail') or result['phase'])
            return result
        time.sleep(.1)
    raise KitControlError('命令没有收到回执；请先查看状态，不要直接重发')


def main(argv=None):
    parser = argparse.ArgumentParser(description='直接调用运行中 Kit 的自动化接口，无需按键或截图')
    parser.add_argument('--game-dir', type=Path, default=DEFAULT_GAME)
    sub = parser.add_subparsers(dest='topic', required=True)
    gravel = sub.add_parser('gravel')
    actions = gravel.add_subparsers(dest='action', required=True)
    actions.add_parser('status')
    for name in ('start', 'config'):
        action = actions.add_parser(name)
        action.add_argument('--radius', type=int)
        action.add_argument('--depth', type=int)
        action.add_argument('--limit', type=int)
    actions.add_parser('stop')
    materials=sub.add_parser('materials',help='材料任务独立 API：补料、制作与投影施工')
    material_actions=materials.add_subparsers(dest='action',required=True)
    start=material_actions.add_parser('start')
    choice=start.add_mutually_exclusive_group(required=True)
    choice.add_argument('--projection',action='store_true')
    choice.add_argument('--item')
    start.add_argument('--count',type=int)
    status=material_actions.add_parser('status');status.add_argument('--job-id')
    for name in ('pause','resume','cancel'):
        control=material_actions.add_parser(name);control.add_argument('--job-id',required=True)
    args = parser.parse_args(argv)
    root = args.game_dir / 'config/twob2tkit/automation'
    if args.topic=='materials':
        from material_task_client import MaterialTaskClient, MaterialTaskError, compact as material_compact
        try:
            client=MaterialTaskClient(root)
            if args.action=='start':
                if args.projection:
                    if args.count is not None:raise MaterialTaskError('投影任务不接受 --count')
                    result=client.start_projection()
                else:
                    if args.count is None:raise MaterialTaskError('单物品任务需要 --count')
                    result=client.start_item(args.item,args.count)
            else:result=getattr(client,args.action)(args.job_id)
            print(json.dumps(material_compact(result),ensure_ascii=False,separators=(',',':')))
            return 0 if result.get('phase')=='done' else 2
        except (OSError,ValueError,KeyError,RuntimeError) as error:
            print(json.dumps({'schema':1,'phase':'error','detail':str(error),
                'submitted':getattr(error,'submitted',False),'id':getattr(error,'request_id',None),
                'op':getattr(error,'op',None)},ensure_ascii=False,separators=(',',':')))
            return 2
    try:
        state = live_status(root)
        if args.action != 'status':
            op = {'start': 'gravel_start', 'config': 'gravel_config', 'stop': 'gravel_stop'}[args.action]
            request = make_request(state, op, **{
                key: getattr(args, key, None) for key in ('radius', 'depth', 'limit')})
            state = send(root, request)
        print(json.dumps(compact(root, state), ensure_ascii=False, separators=(',', ':')))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.exit(2, f'kit-cli: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
