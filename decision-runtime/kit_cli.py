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
    recovery=sub.add_parser('recovery',help='只进食、原地升高和等待回血，不解锁或重连')
    recovery.add_argument('action',choices=('run',))
    recovery.add_argument('--out',type=Path,required=True)
    gravel = sub.add_parser('gravel')
    actions = gravel.add_subparsers(dest='action', required=True)
    actions.add_parser('status')
    for name in ('start', 'config'):
        action = actions.add_parser(name)
        action.add_argument('--radius', type=int)
        action.add_argument('--depth', type=int)
        action.add_argument('--limit', type=int)
    actions.add_parser('stop')
    farm=sub.add_parser('farm',help='共用小田地准备与有界土豆/小麦种植')
    farm_actions=farm.add_subparsers(dest='action',required=True)
    prepare=farm_actions.add_parser('prepare')
    prepare.add_argument('--center',type=int,nargs=3,required=True)
    prepare.add_argument('--radius',type=int,choices=(1,2),default=2)
    prepare.add_argument('--water-source',type=int,nargs=3)
    prepare.add_argument('--max-torches',type=int,choices=(1,2,3,4),default=4)
    prepare.add_argument('--out',type=Path)
    prepare.add_argument('--no-move',action='store_true')
    prepare.add_argument('--recover-read-only-session',action='store_true')
    prepare.add_argument('--reconcile-finish',action='store_true')
    reseed=farm_actions.add_parser('reseed',help='只补原登记田里明确的空耕地，不扩田')
    reseed.add_argument('--registry',type=Path,required=True)
    reseed.add_argument('--cell',type=int,nargs=3,action='append',required=True)
    reseed.add_argument('--out',type=Path)
    reseed.add_argument('--no-move',action='store_true')
    plant=farm_actions.add_parser('plant')
    plant.add_argument('--center',type=int,nargs=3,required=True)
    plant.add_argument('--crop',choices=('potato','wheat'),default='potato')
    plant.add_argument('--radius',type=int,choices=(1,2),default=2)
    plant.add_argument('--max-cells',type=int,choices=range(1,25),default=24)
    plant.add_argument('--out',type=Path)
    plant.add_argument('--no-move',action='store_true')
    materials=sub.add_parser('materials',help='材料任务独立 API：补料、制作与投影施工')
    material_actions=materials.add_subparsers(dest='action',required=True)
    start=material_actions.add_parser('start')
    choice=start.add_mutually_exclusive_group(required=True)
    choice.add_argument('--projection',action='store_true')
    choice.add_argument('--item')
    start.add_argument('--count',type=int)
    audit=material_actions.add_parser('audit',help='完整核验当前投影，不移动或新建材料会话')
    audit.add_argument('--out',type=Path,required=True)
    stock=material_actions.add_parser('stock',help='实机只读核对指定仓库；不取料、寄存或拆潜影盒')
    stock.add_argument('--depot',type=int,nargs=3,action='append',required=True)
    stock.add_argument('--out',type=Path,required=True)
    stock.add_argument('--profile',type=Path)
    status=material_actions.add_parser('status');status.add_argument('--job-id')
    for name in ('pause','resume','cancel'):
        control=material_actions.add_parser(name);control.add_argument('--job-id',required=True)
    idle=sub.add_parser('idle',help='忙时让出、空闲时钓鱼/收田/喂养，本地无模型服务')
    idle.add_argument('action',choices=('template','init','run','status','pause','stop','resume','revalidate-fields'))
    idle.add_argument('--profile',type=Path)
    idle.add_argument('--caretaker-profile',type=Path)
    idle.add_argument('--plant-registry',type=Path,action='append',default=[])
    idle.add_argument('--acknowledge-existing-fields',action='store_true')
    care=sub.add_parser('caretaker',help='本地周期收获、繁殖、烹饪和入箱，无模型调用')
    care.add_argument('action',choices=('run','pause','stop','status','resume'))
    care.add_argument('--profile',type=Path,required=True)
    care.add_argument('--out',type=Path)
    lighting=sub.add_parser('lighting',help='固定配置分区补光，真实扫描与保护停靠；无 AI/UI')
    lighting.add_argument('action',choices=('run','resume','audit','status','pause','stop','reconcile-travel','reconcile-known-travel','reconcile-entity','reconcile-guard','reconcile-own-torch','reconcile-opening','reconcile-network-travel'))
    lighting.add_argument('--profile',type=Path,required=True)
    lighting.add_argument('--out',type=Path)
    lighting.add_argument('--verbose',action='store_true')
    lighting.add_argument('--work-baseline',type=Path)
    lighting.add_argument('--travel-evidence',type=Path)
    lighting.add_argument('--audit-prefix',type=Path)
    lighting.add_argument('--auto-supply',action='store_true')
    lighting.add_argument('--torch-target',type=int,default=128)
    lighting.add_argument('--max-supplies',type=int,default=32)
    replies=sub.add_parser('replies',help='旧只读扫描回包的无损归档与恢复；不发送游戏动作')
    replies.add_argument('--days',type=int,default=7)
    replies.add_argument('--max-files',type=int,default=2000)
    replies.add_argument('--apply',action='store_true')
    replies.add_argument('--restore')
    args = parser.parse_args(argv)
    root = args.game_dir / 'config/twob2tkit/automation'
    if args.topic=='replies':
        from reply_archive import main as archive_main
        command=['--root',str(root),'--days',str(args.days),'--max-files',str(args.max_files)]
        if args.apply:command += ['--apply']
        if args.restore:command += ['--restore',args.restore]
        return archive_main(command)
    if args.topic=='recovery':
        from survival_recovery import recover
        try:
            print(json.dumps(recover(args.game_dir,args.out),ensure_ascii=False));return 0
        except (RuntimeError,ValueError,OSError) as error:
            print(json.dumps({'phase':'waiting','detail':str(error)},ensure_ascii=False));return 2
    if args.topic=='lighting':
        from lighting_regions_cli import main as lighting_main
        command=['--game-dir',str(args.game_dir),'--profile',str(args.profile)]
        if args.out is not None:command += ['--out',str(args.out)]
        if args.verbose:command += ['--verbose']
        if args.work_baseline is not None:command += ['--work-baseline',str(args.work_baseline)]
        if args.travel_evidence is not None:command += ['--travel-evidence',str(args.travel_evidence)]
        if args.audit_prefix is not None:command += ['--audit-prefix',str(args.audit_prefix)]
        if args.auto_supply:command += ['--auto-supply','--torch-target',str(args.torch_target),'--max-supplies',str(args.max_supplies)]
        return lighting_main(command+[args.action])
    if args.topic=='idle':
        from idle_service_cli import main as idle_main
        command=['--game-dir',str(args.game_dir)]
        if args.profile is not None:command += ['--profile',str(args.profile)]
        if args.caretaker_profile is not None:command += ['--caretaker-profile',str(args.caretaker_profile)]
        for path in args.plant_registry:command += ['--plant-registry',str(path)]
        if args.acknowledge_existing_fields:command += ['--acknowledge-existing-fields']
        return idle_main(command+[args.action])
    if args.topic=='caretaker':
        from farm_caretaker_cli import main as caretaker_main
        command=['--game-dir',str(args.game_dir),'--profile',str(args.profile)]
        if args.out is not None:command += ['--out',str(args.out)]
        return caretaker_main(command+[args.action])
    if args.topic=='farm':
        if args.action=='reseed':
            from farm_reseed_cli import main as reseed_main
            command=['--game-dir',str(args.game_dir),'--registry',str(args.registry)]
            for point in args.cell:command += ['--cell',*map(str,point)]
            if args.out is not None:command += ['--out',str(args.out)]
            if args.no_move:command += ['--no-move']
            return reseed_main(command)
        if args.action=='prepare':
            from farm_preparation_cli import main as prepare_main
            command=['--game-dir',str(args.game_dir),'--center',*map(str,args.center),
                     '--radius',str(args.radius),'--max-torches',str(args.max_torches)]
            if args.water_source is not None:command += ['--water-source',*map(str,args.water_source)]
            if args.out is not None:command += ['--out',str(args.out)]
            if args.no_move:command += ['--no-move']
            if args.recover_read_only_session:command += ['--recover-read-only-session']
            if args.reconcile_finish:command += ['--reconcile-finish']
            return prepare_main(command)
        from potato_farm_cli import main as farm_main
        argv=['--game-dir',str(args.game_dir),'--center',*map(str,args.center),
              '--radius',str(args.radius),'--max-cells',str(args.max_cells)]
        if args.crop!='potato':argv += ['--crop',args.crop]
        if args.out is not None:argv += ['--out',str(args.out)]
        if args.no_move:argv += ['--no-move']
        return farm_main(argv)
    if args.topic=='materials':
        if args.action=='stock':
            from warehouse_audit_cli import main as stock_main
            command=['--game-dir',str(args.game_dir),'--out',str(args.out)]
            for pos in args.depot:command+=['--depot',*map(str,pos)]
            if args.profile is not None:command+=['--profile',str(args.profile)]
            return stock_main(command)
        if args.action=='audit':
            from material_audit_cli import main as audit_main
            return audit_main(['--game-dir',str(args.game_dir),'--out',str(args.out)])
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
