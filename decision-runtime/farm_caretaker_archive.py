"""Explicitly abandon an unknown old cycle while preserving its exact evidence.

This is local journal maintenance, not reconciliation or a successful receipt.
It never sends a game request, starts a worker, or changes a safety hold.
"""
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from farm_caretaker import STAGES, validate_profile
from farm_caretaker_review import _read
from kit_runtime.journal import write_json
from material_jobs.protocol import server_key


def _registered(root, profile, out):
    profile = validate_profile(profile)
    key = hashlib.sha256((profile['server']+'|'+profile['dimension']).encode()).hexdigest()[:20]
    home = root/'farm-caretakers'/key
    registry = _read(home/'registry.json'); directory = Path(registry['directory']).resolve()
    if registry.get('profile') != profile or out is not None and Path(out).resolve() != directory:
        raise ValueError('农场登记配置或原记录目录已改变；不采用其它周期')
    return profile, key, home, directory


def _idle(root, profile, old_world, now):
    state = _read(root/'status.json')
    if (type(state.get('time')) is not int or not -1000 <= now-state['time'] <= 2500
            or state.get('connected') is not True or not isinstance(state.get('world_session'),str)
            or not state['world_session'] or server_key(state.get('server')) != profile['server']
            or state.get('dimension') != profile['dimension']
            or type(state.get('control_revision')) is not int or state['control_revision'] < 0):
        raise RuntimeError('归档须有已登记服务器的当前新鲜世界状态')
    if state.get('manual_movement') is not False or state.get('navigating') is not False:
        raise RuntimeError('玩家移动或原生导航尚未停止，不能归档')
    if state.get('phase') not in ('idle','stopped','done','parking','waiting','error'):
        raise RuntimeError('原生动作尚未确认停止，不能归档')
    for flag in ('borer_active','chopping','printing','planter_active','feeder_active','fisher_active',
                 'guard_busy','health_recovery_hold','air_return_active','guard_reconnect_pending'):
        if flag in state and state[flag] is not False:
            raise RuntimeError('仍有活动任务或安全恢复：'+flag)
    if state.get('native_material_busy') not in (None,False):
        raise RuntimeError('原生材料动作仍在执行')
    task = state.get('material_task')
    if (not isinstance(task,dict) or task.get('process_alive') is not False
            or task.get('occupied') is not False or task.get('cancelling') not in (None,False)):
        raise RuntimeError('材料后台尚未确认退出，不能归档')
    for name in ('build_job','concrete','professional_printer','gravel'):
        job = state.get(name) or {}
        if not isinstance(job,dict) or job.get('active') not in (None,False):
            raise RuntimeError('仍有活动任务：'+name)
    hold = state.get('safety_hold') or {}
    if not isinstance(hold,dict) or hold.get('escaping') not in (None,False):
        raise RuntimeError('安全撤离仍在执行，不能归档')
    screen = state.get('screen')
    menu = state.get('menu') or {}; cursor = menu.get('cursor') or {}
    if (not isinstance(screen,str) or screen and not screen.startswith('Kit')
            or menu.get('type') != 'InventoryMenu' or type(cursor.get('count')) is not int
            or cursor['count'] != 0 or cursor.get('item') != 'minecraft:air'):
        raise RuntimeError('请先关闭容器并确认物品光标为空，再归档')
    lease = state.get('supervision_lease') or {}
    if not isinstance(lease,dict):raise RuntimeError('原生租约状态不可读取')
    if lease and (lease.get('kind') != 'parking' or lease.get('world_session') != state['world_session']
                  or lease.get('revision') != state['control_revision'] or state.get('flight') is not True
                  or state.get('guard_armed') is not True or state.get('guard_pve_only') is not True):
        raise RuntimeError('旧作业租约尚未终止或当前停车未确认，不能归档')
    mailbox = root/'request.json'
    if mailbox.exists():
        request = _read(mailbox)
        if (not isinstance(request.get('world_session'),str) or type(request.get('expires_at')) is not int
                or not isinstance(request.get('id'),str)):
            raise RuntimeError('请求邮箱未确认过期或停止，不能归档')
        if (request['world_session'] == state['world_session'] and request['expires_at'] >= now
                and request['id'] != state.get('last_request')):
            raise RuntimeError('当前世界仍有尚未消费的原生请求，不能归档')
    from material_plan import inventory_counts
    counts = dict(inventory_counts(state))
    proof = {'world_session':state['world_session'], 'revision':state['control_revision'],
             'inventory':deepcopy(state['inventory']), 'counts':counts, 'cursor':deepcopy(cursor),
             'lease':deepcopy(lease), 'native_phase':state['phase'],
             'termination_basis':'WORLD_SESSION_ENDED' if state['world_session'] != old_world else 'NATIVE_IDLE_WITHOUT_WORK_LEASE'}
    return state, proof


def _cycle_files(cycle, directory):
    if not cycle.is_dir() or cycle.is_symlink() or not cycle.resolve().is_relative_to(directory):
        raise ValueError('原周期目录无效')
    files=[]; total=0
    for path in sorted(cycle.rglob('*')):
        if path.is_symlink():raise ValueError('原周期包含符号链接，拒绝归档外部证据')
        if not path.is_file():continue
        total += path.stat().st_size;files.append(path)
        if len(files)>1024 or total>64*1024*1024:
            raise ValueError('原周期证据超过归档上限；原记录保留')
    return files


def _references(value, requests, leases):
    if isinstance(value,dict):
        for key,item in value.items():
            if isinstance(item,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',item):
                if key in ('id','request_id','last_request') and item.startswith('materials-'):requests.add(item)
                if key in ('id','lease','supervision_lease','parking_lease') and item.startswith('jev-owner-'):leases.add(item)
            _references(item,requests,leases)
    elif isinstance(value,list):
        for item in value:_references(item,requests,leases)


def _sync_directory(path):
    descriptor=os.open(path,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def archive_pending(automation, profile, out=None, *, acknowledge_unknown_outcome=False,
                    expected_pending_sha256=None, now_ms=None):
    if acknowledge_unknown_outcome is not True:
        raise ValueError('必须明确确认已核对物品安全并接受原结果未知：--acknowledge-unknown-outcome')
    root=Path(automation).resolve();profile,key,home,directory=_registered(root,profile,out)
    lock_path=home/'worker.lock'
    if not lock_path.is_file():raise RuntimeError('原后台工作锁不可读取，不能归档')
    # Opening the existing file for reading and flocking does not create or edit it.
    with lock_path.open('rb') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:raise RuntimeError('周期后台仍持有工作锁，请先停止并等待退出') from error
        book_path=directory/'caretaker.json';raw_book=book_path.read_bytes();digest=hashlib.sha256(raw_book).hexdigest()
        if expected_pending_sha256 is not None and expected_pending_sha256 != digest:
            raise RuntimeError('确认后原周期记录已改变；请重新查看并确认')
        book=_read(book_path);cycle=book.get('current_cycle');pending=book.get('pending')
        if (book.get('profile') != profile or book.get('schema') != 1 or book.get('ai_calls') != 0
                or not isinstance(pending,dict) or not isinstance(cycle,dict)
                or type(cycle.get('id')) is not int or cycle['id'] < 1 or book.get('cycle') != cycle['id']
                or book.get('world_session') != cycle.get('world_session')
                or not isinstance(cycle.get('world_session'),str) or not cycle['world_session']):
            raise ValueError('没有可归档的原未确认周期，或原周期结构无效')
        cycle_dir=directory/('cycle-%06d'%cycle['id'])
        stage=pending.get('stage')
        expected_stage=cycle_dir if stage=='parking' else cycle_dir/stage if stage in STAGES else None
        if (expected_stage is None or Path(cycle.get('directory','')).resolve()!=cycle_dir
                or Path(pending.get('directory','')).resolve()!=expected_stage):
            raise ValueError('未确认动作目录不属于原周期')
        files=_cycle_files(cycle_dir,directory)
        now=lambda:int(time.time()*1000) if now_ms is None else now_ms
        state,proof=_idle(root,profile,cycle['world_session'],now())
        requests=set();leases=set();_references(book,requests,leases)
        for path in files:
            if path.suffix not in ('.json','.jsonl') or path.stat().st_size>2_000_000:continue
            try:
                rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.suffix=='.jsonl' else [json.loads(path.read_text())]
                for value in rows:_references(value,requests,leases)
            except (ValueError,UnicodeError):pass  # Still copy exact original bytes; never invent a receipt.
        archive_root=directory/'archives'
        if archive_root.is_symlink():raise ValueError('归档目录指向外部位置')
        archive_root.mkdir(exist_ok=True)
        destination=archive_root/('cycle-%06d-%s'%(cycle['id'],uuid.uuid4().hex))
        destination.mkdir();evidence={};missing=[];sources={};preserved_bytes=0
        def preserve(source,relative):
            nonlocal preserved_bytes
            if not source.is_file() or source.is_symlink():raise ValueError('原证据无法安全复制：'+str(source))
            data=source.read_bytes()
            preserved_bytes+=len(data)
            if preserved_bytes>128*1024*1024:raise ValueError('原证据超过归档上限')
            target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno())
            saved_hash=hashlib.sha256(data).hexdigest();sources[source]=saved_hash
            evidence[str(relative)]={'sha256':saved_hash,'bytes':len(data)}
        for path in files:preserve(path,Path('cycle')/path.relative_to(cycle_dir))
        preserve(book_path,Path('original-caretaker.json'))
        preserve(home/'registry.json',Path('original-registry.json'))
        control_path=directory/'control.json';control=_read(control_path) if control_path.exists() else None
        if control is not None:
            if control.get('key')!=key or not isinstance(control.get('id'),str):raise ValueError('原控制记录无效')
            preserve(control_path,Path('original-control.json'))
        for name in ('assistant-control-hold.json','safety-hold.json','material-health-hold.json'):
            if (root/name).is_file():preserve(root/name,Path('safety-holds')/name)
        names=['reply-'+rid+'.json' for rid in sorted(requests)]+['supervision-receipt-'+lease+'.json' for lease in sorted(leases)]
        for name in names:
            if (root/name).exists():preserve(root/name,Path('native-evidence')/name)
            else:missing.append(name)
        write_json(destination/'current-observation.json',state)
        record={'schema':1,'state':'abandoned','outcome':'outcome_unknown','cycle_id':cycle['id'],
                'manual_acknowledgement':'I checked item safety and accept the original outcome is unknown',
                'archived_at':now(),'original_book_sha256':digest,'original_pending':deepcopy(pending),
                'original_world_session':cycle['world_session'],'termination_proof':proof,
                'evidence':evidence,'missing_native_evidence':missing,'game_actions_sent':0,'committed':False}
        # Evidence is durable before the coordinator pointer is replaced. Original cycle files stay intact.
        write_json(destination/'archive.json',record)
        _,latest_proof=_idle(root,profile,cycle['world_session'],now())
        if latest_proof!=proof or book_path.read_bytes()!=raw_book:
            raise RuntimeError('复制证据期间状态或原周期改变；原周期保留，请重新确认')
        if control is not None and _read(control_path)!=control:
            raise RuntimeError('复制证据期间控制请求改变；原周期保留')
        if any(not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest for source,digest in sources.items()):
            raise RuntimeError('复制证据期间原记录改变；原周期保留')
        for folder in sorted((p for p in destination.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
            _sync_directory(folder)
        for folder in (destination,archive_root,directory):_sync_directory(folder)
        next_book=deepcopy(book)
        history=next_book.setdefault('archived_cycles',[])
        if not isinstance(history,list):raise ValueError('原归档历史无效')
        history.append({'cycle_id':cycle['id'],'archive':str(destination),'state':'abandoned',
                        'outcome':'outcome_unknown','original_book_sha256':digest})
        next_book.update(enabled=False,paused=True,reason='ARCHIVED_PENDING_MANUAL',pending=None,
                         current_cycle=None,stage=STAGES[0],next_due=0,world_session=None,last_revision=None)
        for name in ('parking_lease','acknowledged_stop','manual_stop','resume_wait','cleanup_wait'):
            next_book.pop(name,None)
        if control is not None:next_book['last_control']=control['id']
        write_json(book_path,next_book)
        _sync_directory(directory)
        record['committed']=True
        result={'phase':'archived','state':'abandoned','outcome':'outcome_unknown','archive':str(destination),
                'next_cycle':cycle['id']+1,'worker_started':False,'game_actions_sent':0,'ai_calls':0,
                'detail':'旧周期已按人工确认归档为结果未知；再次点击开始本地周期，才会使用当前新鲜库存新建下一轮。安全锁保持原状态。'}
        try:write_json(destination/'archive.json',record)
        except OSError as error:result['archive_marker_warning']='原记录和调度指针已保存；归档最终标记写入失败：'+str(error)
        return result
