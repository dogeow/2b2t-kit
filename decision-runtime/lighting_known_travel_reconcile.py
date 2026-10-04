"""Archive one known nonmutating AirOnly stop after separately proved recovery.

This entry reads evidence and writes an archive/journal only. It never sends a
game request, recovers a player, repeats navigation or starts another batch.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex

from lighting_cli import scan_cells
from lighting_regions_cli import RegionsPaused
from lighting_work_baseline import identity

DETAIL='air-only path changed; no blocks were excavated'
ORIGINAL=('original-regions.json','original-terminal-status.json','original-request.json',
          'original-events.jsonl','original-run-manifest.json','original-movement-failure.json',
          'original-arrival-height-plan.json')


def require(condition,detail):
    if not condition:raise RegionsPaused(detail)


def inventory(frame):
    rows=frame.get('inventory')
    require(isinstance(rows,list)and len(rows)>=36,'Complete original player inventory is unavailable')
    slots=[row.get('slot')for row in rows if isinstance(row,dict)]
    require(len(slots)==len(rows)and all(type(v)is int and 0<=v<=50 for v in slots)
            and len(set(slots))==len(slots)and set(range(36))<=set(slots),
            'Original inventory slot coverage differs')
    require(all(isinstance(row.get('item'),str)and type(row.get('count'))is int and row['count']>=0 for row in rows),
            'Original inventory counts are unavailable')
    return sorted(deepcopy(rows),key=lambda row:row['slot'])


def reconcile(worker,manifest_path,*,process_probe=None):
    require(manifest_path is not None,'Original known-travel evidence manifest is required')
    source=Path(manifest_path)
    require(source.name=='manifest.json'and not source.is_symlink(),'Exact retained known-travel manifest is required')
    base=source.parent.resolve();captured={}

    def read(path,*,lines=False):
        path=Path(path)
        require(not path.is_symlink()and path.is_file()and path.stat().st_size<=8*1024*1024,
                'Bounded original known-travel evidence is unavailable')
        raw=path.read_bytes();captured[path]=raw
        value=[json.loads(row)for row in raw.splitlines()if row.strip()]if lines else json.loads(raw)
        require(isinstance(value,list)and all(isinstance(v,dict)for v in value)if lines else isinstance(value,(dict,list)),
                'Original known-travel evidence shape differs')
        return value

    with worker.worker_lock():
        original_book_bytes=worker.path.read_bytes()
        require(json.loads(original_book_bytes)==worker.book,'Original lighting journal changed')
        book=worker.book;pending=deepcopy(book.get('pending'))
        require(isinstance(pending,dict)and pending.get('stage')=='travel'and pending.get('travel_stage')=='arrival'
                and pending.get('mode')=='lighting'and type(pending.get('region_index'))is int
                and pending['region_index']==book.get('cursor')and 0<=pending['region_index']<len(worker.profile['regions'])
                and pending.get('error')=='Unavailable: 前往资源区的空气航线未确认：'+DETAIL,
                'Only the exact known AirOnly arrival stop may be reconciled')
        native=pending.get('native_request')or{};rid=native.get('request_id')
        world,task,lease=pending.get('world_session'),pending.get('task_session'),pending.get('lease')
        require(all(isinstance(v,str)and v for v in (rid,world,task,lease))
                and all(re.fullmatch(r'[A-Za-z0-9_-]{1,96}',v)for v in (rid,task,lease))
                and set(native)=={'request_id','op','world_session','task_session','lease_id','base_revision','expected_revision'}
                and native.get('op')=='navigate'and native.get('world_session')==world
                and native.get('task_session')==task and native.get('lease_id')==lease
                and type(native.get('base_revision'))is int and native.get('expected_revision')==native['base_revision']+1
                and pending.get('uncertain_request')==native,'Original native request identity differs')
        revision=native['expected_revision']
        directory=Path(pending.get('directory',''))
        require(not directory.is_symlink()and directory.resolve()==(worker.out/'batch-'/f"{book['dispatch_sequence']:05d}").resolve(),
                'Original known-travel batch directory differs')
        manifest=read(source);require(isinstance(manifest,dict),'Original manifest is unavailable')
        require(manifest.get('world_session')==world and manifest.get('request_id')==rid
                and manifest.get('original_reply_exists')is False and manifest.get('original_request_replayed')is False
                and Path(manifest.get('source_directory','')).resolve()==directory.resolve()
                and set(manifest.get('files_sha256',{}))==set(ORIGINAL),'Original preserved manifest scope differs')
        originals={}
        for name in ORIGINAL:
            originals[name]=read(base/name,lines=name.endswith('.jsonl'))
            require(hashlib.sha256(captured[base/name]).hexdigest()==manifest['files_sha256'][name],
                    'Original preserved evidence hash differs')
        prior=originals['original-regions.json'];terminal=originals['original-terminal-status.json']
        request=originals['original-request.json'];events=originals['original-events.jsonl']
        run=originals['original-run-manifest.json']
        def stable_book(value):
            value=deepcopy(value);value.pop('phase',None);value.pop('reason',None)
            if isinstance(value.get('pending'),dict):value['pending'].pop('waiting_observation',None)
            return value
        require(stable_book(prior)==stable_book(book)and prior.get('phase')=='waiting_unresolved'
                and book.get('phase')in ('waiting','waiting_unresolved')and prior.get('profile')==worker.profile
                and book.get('world_session')==world and book.get('ai_calls')==0,
                'Campaign, cursor, profile, placement history or original pending changed')
        require(request.get('id')==rid and request.get('op')=='navigate'and request.get('world_session')==world
                and request.get('task_session')==task and request.get('expected_revision')==native['base_revision']
                and request.get('air_only')is True and request.get('background_ok')is True,
                'Preserved original mailbox does not prove this AirOnly request')
        require(events and len({e.get('request_id')for e in events})==len(events)
                and events[-1].get('request_id')==rid and events[-1].get('phase')=='waiting'
                and events[-1].get('detail')==DETAIL and events[-1].get('op')=='navigate'
                and events[-1].get('revision_before')==native['base_revision']
                and events[-1].get('revision_after')==revision,'Exact original native WAITING event is unavailable')
        for event in events:
            params=event.get('params')or{}
            require(event.get('world_session')==world and event.get('inventory_delta')=={}
                    and event.get('health_before')==20 and event.get('health_after')==20
                    and event.get('op')in ('scan','snapshot','material_session','navigate')
                    and event.get('phase')in ((None,'done')if event.get('op')=='snapshot'else('waiting',)if event is events[-1]else('done',))
                    and params.get('task_session')in ((None,task)if event.get('op')in ('scan','snapshot')else(task,))
                    and (event.get('op')!='navigate'or params.get('air_only')is True),
                    'Original journal includes unknown actions, construction or inventory mutation')
        last=events[-1]
        require(all(request.get(key)==value for key,value in last['params'].items())
                and terminal.get('id')==rid and terminal.get('last_request')==rid and terminal.get('op')=='navigate'
                and terminal.get('phase')=='waiting'and terminal.get('detail')==DETAIL
                and terminal.get('control_revision')==revision and not terminal.get('navigating')
                and not terminal.get('native_material_busy')and not terminal.get('pending_scan')
                and type(terminal.get('time'))is int and terminal['time']>=last['time']*1000
                and run.get('task_session')==task and run.get('world_session')==world and run.get('complete')is False,
                'Preserved exact status/mailbox does not prove the known terminal request')
        named=worker.root/('reply-'+rid+'.json')
        if named.exists():
            reply=read(named)
            require(all(reply.get(k)==terminal.get(k)for k in ('id','world_session','control_revision','phase','detail')),
                    'Retained named original reply contradicts the preserved native terminal')
        for saved,live in (('original-events.jsonl','events.jsonl'),
                           ('original-run-manifest.json','run-manifest-'+task+'.json'),
                           ('original-arrival-height-plan.json','arrival-height-plan.json'),
                           ('original-movement-failure.json','movement-failure-'+rid+'.json')):
            read(directory/live,lines=live.endswith('.jsonl'))
            require(captured[base/saved]==captured[directory/live],'Original live batch evidence changed')
        require(not (directory/'report.json').exists()and not (directory/'current-region-audit.json').exists()
                and not list(directory.rglob('inflight.json')),'Original placement or unknown work exists')
        for path in (worker.root/'lighting-intents').glob('*.json'):
            intent=read(path)
            require(not (intent.get('world_session')==world and intent.get('task_session')==task),
                    'An original placement intent remains')

        observed=base/'column-observation-002';maintenance=base/'owned-ascent-001'
        probe_before=read(observed/'before.json');probe_reply=read(observed/'full-body-column-reply.json')
        probe_after=read(observed/'after.json');probe_events=read(observed/'events.jsonl',lines=True)
        before=read(maintenance/'before.json');column=read(maintenance/'fresh-full-body-column-reply.json')
        park=read(maintenance/'native-park-target-reply.json');ascent=read(maintenance/'native-ascent-reply.json')
        plan=read(maintenance/'plan.json');actions=read(maintenance/'events.jsonl',lines=True)
        settled=read(maintenance/'settled-frames.json');hover=read(maintenance/'verified-high-hover.json')
        stop_before=read(maintenance/'before-worker-stop.json');stopped=read(maintenance/'worker-stop.json')
        parked=read(maintenance/'after-native-parking.json');park_frames=read(maintenance/'parking-frames.json')
        keep=read(maintenance/'native-keep-receipt.json')
        canonical=worker.root/('supervision-receipt-'+lease+'.json');read(canonical)
        require(captured[canonical]==captured[maintenance/'native-keep-receipt.json'],'Canonical native KEEP differs from its preserved original')
        current=worker._parked_observation(expected_world=world)
        expected_identity=identity(terminal)
        require(expected_identity['player_uuid']and isinstance(expected_identity['projection_selection'],dict)
                and expected_identity['server']==worker.profile['server']and expected_identity['dimension']==worker.profile['dimension']
                and run.get('placement_key')==expected_identity['projection_selection'].get('key'),
                'Original player/model identity is unavailable')
        selection=book.get('work_selection')or{}
        if selection.get('campaign')==book.get('campaign'):
            require(selection.get('identity')==expected_identity,'Original directed-work player/model scope changed')
        old_inventory,new_inventory=inventory(terminal),inventory(before);wear=[]
        require(len(old_inventory)==len(new_inventory),'Original inventory slot count changed')
        for old,new in zip(old_inventory,new_inventory):
            if old==new:continue
            a,b=deepcopy(old),deepcopy(new);od,nd=a.pop('durability',None),b.pop('durability',None)
            require(a==b and old['item']in ('minecraft:diamond_sword','minecraft:bow')and old['count']==1
                    and type(od)is int and type(nd)is int and od-nd==1,'Recovery inventory changed beyond exact defense tool wear')
            wear.append({'slot':old['slot'],'item':old['item'],'before':od,'after':nd})
        require(len(wear)<=2,'Original defense wear exceeds this narrow recovery proof')

        def frame(value,rev,kind,*,stock_frame=True,scan_snapshot=False):
            require(isinstance(value,dict)and identity(value)==expected_identity and value.get('connected')is True
                    and value.get('health')==20 and value.get('food',0)>=18 and value.get('manual_movement')is False
                    and value.get('under_water')is False and not value.get('screen')
                    and all(value.get(k)is True for k in ('flight','guard_armed','guard_pve_only'))
                    and not any(value.get(k)for k in ('navigating','native_material_busy','guard_busy',
                                                     'borer_active','printing','chopping','planter_active','feeder_active','fisher_active'))
                    and not (value.get('safety_hold')or{}).get('active')
                    and value.get('recent_hurt_at')==terminal.get('recent_hurt_at')
                    and type(value.get('time'))is int and type(value.get('control_revision'))is int
                    and value['control_revision']==rev,'Original recovery survival, identity or control scope changed')
            residue=value.get('pending_scan')
            if residue is not None:
                require(scan_snapshot and isinstance(residue,dict)and value.get('phase')=='done'
                        and residue.get('id')==value.get('id')and residue.get('world_session')==world
                        and all(type(residue.get(k))is int for k in ('control_revision','cells_read','total_cells'))
                        and residue.get('control_revision')==rev
                        and residue.get('cells_read')==value.get('scan_cells_read')
                        and residue.get('total_cells')==value.get('scan_total_cells')
                        and residue.get('cells_read')==residue.get('total_cells')
                        and residue.get('reading_complete')is False and residue.get('reply_write_state')=='not_submitted',
                        'Only the exact full terminal scan construction residue is allowed')
            owned=value.get('supervision_lease')or{}
            position=value.get('pos')
            require(isinstance(position,list)and len(position)==3
                    and all(type(v)in(int,float)and math.isfinite(v)for v in position),'Original recovery position is unavailable')
            require(all(owned.get(k)==v for k,v in (('id',lease),('job_session',task),('world_session',world),
                    ('kind',kind),('revision',rev),('remote_finish','guard'))),'Recovery owner lease changed')
            require(not any(e.get('hostile')is True and e.get('alive')is not False for e in value.get('entities',[])),
                    'Recovery still has a currently observed hostile')
            require(value.get('equipment')==terminal.get('equipment')and (not stock_frame or inventory(value)==new_inventory),
                    'Recovery full inventory/components or equipment changed')
        frame(terminal,revision,'materials',stock_frame=False)
        for value in (probe_before,probe_after,before,park):frame(value,revision,'materials')
        for value in (probe_reply,column):frame(value,revision,'materials',scan_snapshot=True)
        require(isinstance(settled,list)and len(settled)==3 and isinstance(park_frames,list)and len(park_frames)==3,
                'Three distinct original settlement/parking frames are required')
        for value in [ascent,*settled,hover,stop_before]:frame(value,revision+1,'materials')
        require(isinstance(keep.get('snapshot'),dict),'Original native KEEP snapshot is unavailable')
        for value in [keep['snapshot'],*park_frames,parked,current]:frame(value,revision+2,'parking')
        for group in (settled,park_frames):
            require(all(group[i]['time']<group[i+1]['time']for i in range(2))
                    and group[-1]['time']-group[0]['time']>=400
                    and all(math.dist(v['pos'],group[0]['pos'])<=.15 for v in group),
                    'Original parking observations are not distinct stable frames')
        require(probe_before.get('last_request')==rid and probe_after.get('last_request')==probe_reply.get('id')
                and before.get('last_request')==probe_reply.get('id')and probe_before['time']>=terminal['time']
                and probe_after['time']>=probe_reply['time']and before['time']>=probe_after['time']
                and park['time']>=column['time'],'Maintenance read chain differs from the preserved original request')
        failure=originals['original-movement-failure.json']
        require(failure.get('op')=='navigate'and failure.get('params')==last['params']and failure.get('detail')==DETAIL
                and failure.get('terminal_pos')==last.get('position_after'),
                'Original movement-failure witness differs from the known native request')
        require(len(probe_events)==1 and probe_events[0].get('request_id')==probe_reply.get('id')
                and len(actions)==3 and [e.get('op')for e in actions]==['scan','material_job_park','navigate']
                and [e.get('request_id')for e in actions]==[column.get('id'),park.get('id'),ascent.get('id')]
                and len({rid,probe_reply.get('id'),column.get('id'),park.get('id'),ascent.get('id')})==5,
                'Maintenance contains extra operations or repeats an original request')
        for event in probe_events+actions:
            require(event.get('phase')=='done'and event.get('world_session')==world
                    and event.get('params',{}).get('task_session')==task and event.get('inventory_delta')=={}
                    and event.get('health_before')==20 and event.get('health_after')==20
                    and event.get('revision_before')==revision
                    and event.get('revision_after')==(revision+1 if event.get('op')=='navigate'else revision),
                    'Maintenance has an unknown terminal or inventory mutation')
        require(plan.get('world_session')==world and plan.get('task_session')==task and plan.get('lease')==lease
                and plan.get('revision')==revision and plan.get('original_request_replayed')is False,
                'Original maintenance plan scope differs')
        origin,target=before.get('pos'),plan.get('target')
        require(all(isinstance(p,list)and len(p)==3 and all(type(v)in(int,float)and math.isfinite(v)for v in p)
                    for p in (origin,target))and plan.get('origin')==origin
                and origin[0]==target[0]and origin[2]==target[2]and 2<target[1]-origin[1]<=31,
                'Maintenance was not one bounded vertical safety ascent')
        for reply,event,start in ((probe_reply,probe_events[0],probe_before['pos']),(column,actions[0],origin)):
            low=[math.floor(start[0]-.35),-64,math.floor(start[2]-.35)]
            high=[math.floor(start[0]+.35),319,math.floor(start[2]+.35)]
            total=math.prod(b-a+1 for a,b in zip(low,high));params=event['params']
            try:host=tuple(int(v)for v in reply.get('kit_version','').split('.'))
            except (ValueError,AttributeError):host=()
            require(reply.get('phase')=='done'and reply.get('world_session')==world
                    and host>=(2026,10,4,1)
                    and params.get('min')==low and params.get('max')==high and params.get('details')is True
                    and all(type(reply.get(k))is int and reply[k]==revision for k in ('scan_start_revision','scan_end_revision'))
                    and type(reply.get('scan_cells_read'))is int and reply['scan_cells_read']==total
                    and type(reply.get('scan_total_cells'))is int and reply['scan_total_cells']==total
                    and reply.get('scan_entities')==[],
                    'Maintenance full current server body/clear entity column is unavailable')
            cells=scan_cells(reply,low,high,world)
            require(all(type(row.get('fluid'))is bool and type(row.get('passable'))is bool for row in cells.values()),
                    'Maintenance body column details are incomplete')
        ground=max((row['pos'][1]+1 for row in column['blocks']if row['fluid']or not row['passable']),default=None)
        require(ground is not None and plan.get('ground_top')==ground
                and target[1]==max(last['position_before'][1],ground+24,origin[1]+3)
                and math.isclose(plan.get('distance',0),math.dist(origin,target),abs_tol=1e-8),
                'Actual maintenance target/ground clearance plan differs')
        lo=[math.floor(origin[0]-.35),math.floor(origin[1]),math.floor(origin[2]-.35)]
        hi=[math.floor(origin[0]+.35),math.floor(target[1]+1.8),math.floor(origin[2]+.35)]
        movement=worker.profile['movement_bounds']
        require(plan.get('ascent_bounds')==[lo,hi]and all(movement['min'][i]<=lo[i]<=hi[i]<=movement['max'][i]for i in range(3))
                and not any(all(lo[i]<=row['pos'][i]<=hi[i]for i in range(3))for row in column['blocks']),
                'Maintenance actual ascent body corridor is obstructed or outside authorization')
        require(actions[1]['params'].get('park_target')==target and park.get('phase')=='done'
                and park['supervision_lease'].get('park_target')==target
                and actions[2]['params'].get('target')==target and actions[2]['params'].get('air_only')is True
                and ascent.get('phase')=='done'and ascent.get('id')==ascent.get('last_request')
                and ascent['time']>=column['scan_ended_at'],'Exact native target update/ascent DONE is unavailable')
        for value in [ascent,*settled,hover,stop_before,*park_frames,parked,current]:
            require(value.get('last_request')==ascent['id']and math.dist(value['pos'],target)<=.55
                    and value['pos'][1]-ground>=20
                    and all(lo[i]<=math.floor(value['pos'][i]-.35)<=math.floor(value['pos'][i]+.35)<=hi[i]for i in (0,2)),
                    'Original ascent/current high parking is not actually settled and clear')
        require(stopped.get('signal')=='SIGINT'and stopped.get('reason')=='known_terminal_nonmutating_travel_after_same_owner_vertical_safety_ascent'
                and stopped.get('request_replayed')is False and stopped.get('original_request_id')==rid
                and stopped.get('ascent_request_id')==ascent['id']and stopped.get('world_session')==world
                and stopped.get('task_session')==task and stopped.get('lease')==lease
                and type(stopped.get('pid'))is int and stopped['pid']>0
                and type(stopped.get('time'))is int and hover['time']<=stop_before['time']<=stopped['time'],
                'Explicit stopped old observation worker evidence is unavailable')
        command=shlex.split(stopped.get('command',''))
        require('lighting'in command and 'resume'in command and '--out'in command
                and Path(command[command.index('--out')+1]).resolve()==worker.out.resolve(),
                'Stopped process is not the original lighting resume worker')
        if process_probe is not None:alive=process_probe(stopped['pid'])
        else:
            try:os.kill(stopped['pid'],0);alive=True
            except ProcessLookupError:alive=False
            except PermissionError:alive=True
        require(alive is False,'The original observation worker is still alive')
        require(keep.get('lease')==lease and keep.get('job_session')==task and keep.get('action')=='KEEP_PVE_GUARD'
                and keep.get('cause')=='heartbeat_lost'and type(keep.get('time'))is int
                and stopped['time']<=keep['time']<=park_frames[0]['time']
                and not keep.get('local_verified')and not keep.get('lease_transition_pending'),
                'Exact original native heartbeat-lost KEEP receipt is unavailable')
        current=worker._parked_observation(expected_world=world)
        frame(current,revision+2,'parking')
        require(current.get('last_request')==ascent['id']and math.dist(current['pos'],target)<=.55
                and current['pos'][1]-ground>=20
                and all(lo[i]<=math.floor(current['pos'][i]-.35)<=math.floor(current['pos'][i]+.35)<=hi[i]for i in (0,2)),
                'Latest original-owner high parking changed before archiving')
        for value in [*park_frames,parked,current]:
            safety=value.get('supervision_safety')or{};owned=value['supervision_lease'];keys=value.get('movement_keys')or{}
            require(all(safety.get(k)==keep[k]for k in ('lease','job_session','action','cause','time'))
                    and owned.get('parked_at')==keep['time']and math.dist(value['pos'],owned.get('park_target',[]))<=.6
                    and keys and all(v is False for v in keys.values()),'Current original-owner native parking confirmation differs')
        mailbox=worker.root/'request.json'
        if mailbox.exists():
            active=read(mailbox)
            require(isinstance(active.get('id'),str)and active['id']==current.get('last_request')
                    and active.get('world_session')==world,'An unacknowledged original/foreign mailbox remains')
        require(all(path.read_bytes()==raw for path,raw in captured.items())and worker.path.read_bytes()==original_book_bytes,
                'Original recovery evidence or lighting journal changed during validation')
        archive=worker.out/'known-travel-reconciliations'/(rid+'-'+str(current['time']))
        preserved={'current-regions.json':original_book_bytes,
                   'current-parking.json':json.dumps(current,ensure_ascii=False,indent=2).encode()}
        for path,raw in captured.items():
            name=str(Path('evidence')/path.relative_to(base))if path.is_relative_to(base)else str(Path('native'if path==canonical else'original-batch')/path.name)
            require(name not in preserved or preserved[name]==raw,'Archive filename collision');preserved[name]=raw
        for name,raw in preserved.items():
            target_path=archive/name;target_path.parent.mkdir(parents=True,exist_ok=True)
            require(not target_path.exists()or target_path.read_bytes()==raw,'Original archived recovery evidence differs')
            if not target_path.exists():target_path.write_bytes(raw)
        record={'outcome':'known_air_only_travel_stopped_then_owned_vertical_park_verified',
                'original_navigation_completed':False,'construction_completed':False,'region_completed':False,
                'request_replayed':False,'placement_credit':0,'original_pending':pending,'original_request_id':rid,
                'maintenance_ascent_request_id':ascent['id'],'native_parking_confirmed':True,
                'archive':str(archive),'world_session':world,'observed_at':current['time'],
                'cursor_preserved':book['cursor'],'defense_tool_wear':wear,
                'evidence_sha256':{name:hashlib.sha256(raw).hexdigest()for name,raw in preserved.items()}}
        previous=worker.book;worker.book=deepcopy(previous)
        worker.book.setdefault('pending_reconciliations',[]).append(record)
        worker.book.update(pending=None,phase='waiting_resume',last_revision=None,parking_lease=None,
                           coverage_complete=False,goal_complete=False,reason='Known travel archived after verified owned parking; explicit resume required')
        try:worker.save()
        except BaseException:worker.book=previous;raise
    return worker.status()
