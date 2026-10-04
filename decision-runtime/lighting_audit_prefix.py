"""Validate a retained current audit wave before continuing its next region.

Every read is evidence validation only. A prefix is not a new scan, placement,
complete coverage or permission to reconcile an unresolved native operation.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from lighting_cli import (EVIDENCE,bounds,later_torch_frame,point,risk_counts,scan_cells,stock,
                          validate_native_details)
from lighting_regions_cli import RegionsPaused
from lighting_work_baseline import current_identity,identity


def require(value,detail):
    if not value:raise RegionsPaused(detail)


def no_pending(root,state):
    require(state.get('pending_scan')is None,'An original scan remains pending')
    mailbox=Path(root)/'request.json'
    if mailbox.exists():
        value=json.loads(mailbox.read_text());last=state.get('last_request')
        require(isinstance(value,dict)and isinstance(value.get('id'),str)and value['id']
                and isinstance(last,str)and last and value['id']==last
                and value.get('world_session')==state['world_session'],'An original native mailbox remains unresolved')
    for path in (Path(root)/'lighting-intents').glob('*.json'):
        value=json.loads(path.read_text())
        require(isinstance(value,dict)and isinstance(value.get('world_session'),str),
                'An original torch intent has unknown scope')
        require(value['world_session']!=state['world_session']or value.get('state')=='verified',
                'An original same-world torch intent remains unresolved')


def validate(worker,path,current):
    require(path is not None,'Retained audit-prefix snapshot is required')
    path=Path(path)
    require(not path.is_symlink()and path.resolve()!=worker.path.resolve(),
            'Use a retained prefix snapshot, not the mutable current journal')
    observed=current_identity(current);no_pending(worker.root,current)
    current_book_bytes=worker.path.read_bytes()
    require(json.loads(current_book_bytes)==worker.book,'Current audit journal changed before prefix validation')
    captured={}
    def read(source,*,lines=False):
        source=Path(source)
        require(not source.is_symlink()and source.is_file()and source.stat().st_size<=8*1024*1024,
                'Bounded original audit-prefix evidence is unavailable')
        raw=source.read_bytes();captured[source]=raw
        value=[json.loads(row)for row in raw.splitlines()if row.strip()]if lines else json.loads(raw)
        require(isinstance(value,list)and all(isinstance(v,dict)for v in value)if lines else isinstance(value,dict),
                'Original audit-prefix evidence is malformed')
        return value
    prefix=read(path);book=worker.book;audits=prefix.get('audits');campaign=book.get('campaign')
    require(book.get('pending')is None and prefix.get('pending')is None
            and type(campaign)is int and campaign>=1
            and prefix.get('schema')==1 and prefix.get('world_session')==observed['world_session']
            and observed['server']==worker.profile['server']and observed['dimension']==worker.profile['dimension']
            and all(prefix.get(k)==book.get(k)for k in ('profile','world_session','campaign','cursor','dispatch_sequence',
                    'batches','audits','work_selection','work_skips','pending_reconciliations'))
            and prefix.get('profile')==worker.profile and book.get('cursor')==len(worker.profile['regions'])
            and isinstance(audits,list)and 1<=len(audits)<=len(worker.profile['regions'])
            and (len(audits)==len(worker.profile['regions'])or prefix.get('coverage_complete')is False)
            and prefix.get('ai_calls')==book.get('ai_calls')==0,
            'Only this unchanged current campaign/wave may reuse a verified audit prefix')
    selection=book.get('work_selection')or{}
    if selection.get('campaign')==campaign:
        require(selection.get('identity')==observed,'Audit prefix differs from the original directed identity')
    def directory(row,kind):
        value=Path(row.get('directory',''))
        require(not value.is_symlink()and value.parent.resolve()==(worker.out/kind).resolve()
                and re.fullmatch(r'[0-9]{5}',value.name),'Original prefix/work directory scope differs')
        return value,int(value.name)
    work=[row for row in book.get('batches',[])if row.get('campaign')==campaign]
    require(work,'Current campaign has no original work-wave boundary')
    last_work=0;last_torch=0;torch_records=[]
    for batch in work:
        require(type(batch.get('campaign'))is int and type(batch.get('placed_verified'))is int
                and 0<=batch['placed_verified']<=64,'Original work placement count is unavailable')
        source,sequence=directory(batch,'batch-');last_work=max(last_work,sequence)
        if batch['placed_verified']==0:continue
        report=read(source/'report.json');placed=report.get('placed');task=report.get('task_session')
        require(report.get('world_session')==observed['world_session']and isinstance(task,str)and task
                and report.get('evidence_scope')==EVIDENCE and isinstance(placed,list)
                and len(placed)==batch['placed_verified'],'Original campaign torch report differs')
        events=read(source/'events.jsonl',lines=True)
        for index,intent in enumerate(placed):
            target=point(intent.get('target'));support=point(intent.get('support'))
            require(target==(support[0],support[1]+1,support[2])and intent.get('world_session')==observed['world_session']
                    and intent.get('task_session')==task and intent.get('state')=='verified'
                    and intent.get('evidence_scope')==EVIDENCE and intent.get('later_verified_frames')==2
                    and type(intent.get('before_stock'))is int and type(intent.get('after_stock'))is int
                    and intent['before_stock']-intent['after_stock']==1 and intent['after_stock']>=0
                    and type(intent.get('before_time'))is int and type(intent.get('after_time'))is int
                    and intent['before_time']<intent['after_time'],'Last actual campaign torch proof is incomplete')
            before=read(source/f'inventory-before-{index}.json');ack=read(source/f'interaction-{index}.json')
            exact=[event for event in events if event.get('request_id')==intent.get('interaction_request')]
            require(identity(before)==observed and before.get('time')==intent['before_time']
                    and stock(before)==intent['before_stock']and ack.get('id')==intent.get('interaction_request')
                    and ack.get('phase')=='done'and identity(ack)==observed
                    and len(exact)==1 and exact[0].get('op')=='interact'and exact[0].get('phase')=='done'
                    and exact[0].get('world_session')==observed['world_session']
                    and exact[0].get('params',{}).get('pos')==list(support)
                    and exact[0].get('params',{}).get('task_session')==task
                    and exact[0].get('params',{}).get('expected_hand')=='minecraft:torch',
                    'Last campaign torch lacks the exact original interaction receipt')
            previous=intent['before_time']
            for frame_index in (1,2):
                raw=read(source/f'actual-torch-{index}-frame-{frame_index}.json')
                inventory=read(source/f'inventory-after-{index}-frame-{frame_index}.json')
                require(identity(raw)==identity(inventory)==observed
                        and later_torch_frame(raw,inventory,target,observed['world_session'],intent['before_stock'],previous)
                        and inventory.get('health')==20 and inventory.get('manual_movement')is False
                        and (inventory.get('supervision_lease')or{}).get('job_session')==task
                        and all(type(raw.get(k))is int for k in ('scan_cells_read','scan_total_cells',
                                  'control_revision','scan_start_revision','scan_end_revision'))
                        and raw['scan_cells_read']==raw['scan_total_cells']==1
                        and raw['control_revision']==raw['scan_start_revision']==raw['scan_end_revision']==inventory.get('control_revision'),
                        'Original two later native torch/inventory frames are unavailable')
                previous=inventory['time']
            require(previous==intent['after_time'],'Original final torch timestamp differs from its actual frame')
            last_torch=max(last_torch,previous)
            torch_records.append({'directory':str(source),'interaction_request':intent['interaction_request'],'after_time':previous})
    last_final=None;raw_ids=[]
    for index,audit in enumerate(audits):
        require(type(audit.get('region_index'))is int and audit['region_index']==index
                and type(audit.get('campaign'))is int and audit['campaign']==campaign
                and audit.get('park_native_confirmed')is True,'Current audit prefix has a gap/foreign campaign')
        source,sequence=directory(audit,'audit-')
        require(sequence==last_work+index+1,'Audit prefix is not the contiguous current work-following wave')
        raw=read(source/'current-region-audit.json');final=read(source/'final-snapshot.json')
        events=read(source/'events.jsonl',lines=True);safety=read(source/'stock-safety.json')
        low,high=bounds(worker.profile['regions'][index]['min'],worker.profile['regions'][index]['max'])
        total=math.prod(b-a+1 for a,b in zip(low,high));lease=raw.get('supervision_lease')or{}
        try:host=tuple(int(v)for v in raw.get('kit_version','').split('.'))
        except (ValueError,AttributeError):host=()
        require(host>=(2026,10,4,1)and identity(raw)==identity(final)==observed
                and raw.get('connected')is True and raw.get('phase')=='done'and isinstance(raw.get('id'),str)
                and raw['id']and raw['id']not in raw_ids
                and all(type(raw.get(k))is int for k in ('control_revision','scan_start_revision','scan_end_revision',
                    'scan_cells_read','scan_total_cells','scan_started_at','scan_ended_at'))
                and raw['control_revision']==raw['scan_start_revision']==raw['scan_end_revision']
                and raw['scan_cells_read']==raw['scan_total_cells']==total
                and 0<raw['scan_started_at']<=raw['scan_ended_at']and raw['scan_started_at']>last_torch
                and audit.get('observed_at')==raw['scan_ended_at']
                and lease.get('kind')=='materials'and lease.get('revision')==raw['control_revision']
                and lease.get('world_session')==observed['world_session']and isinstance(lease.get('id'),str)
                and isinstance(lease.get('job_session'),str)
                and re.fullmatch(r'[A-Za-z0-9_-]{1,96}',lease['id'])and re.fullmatch(r'[A-Za-z0-9_-]{1,96}',lease['job_session']),
                'Complete post-torch current native audit scan is unavailable')
        exact=[event for event in events if event.get('request_id')==raw['id']]
        require(len(exact)==1 and all(event.get('op')in ('scan','snapshot','navigate','material_session','material_job_park')
                and event.get('phase')in ((None,'done')if event.get('op')=='snapshot'else('done',))
                and event.get('inventory_delta')=={} and event.get('world_session')==observed['world_session']
                and event.get('health_before')==event.get('health_after')==20
                and event.get('params',{}).get('task_session')in
                    ((None,lease['job_session'])if event.get('op')in ('scan','snapshot')else(lease['job_session'],))
                and (event.get('op')!='navigate'or event.get('params',{}).get('air_only')is True)
                for event in events),'Prefix audit has unknown/mutating actions or lacks its exact scan')
        event=exact[0];params=event.get('params')or{}
        require(event.get('op')=='scan'and event.get('phase')=='done'
                and params.get('min')==list(low)and params.get('max')==list(high)and params.get('details')is True
                and params.get('task_session')==lease['job_session']
                and event.get('revision_before')==event.get('revision_after')==raw['control_revision'],
                'Prefix original scan request bounds/task/revision differ')
        actual=risk_counts(validate_native_details(scan_cells(raw,low,high,observed['world_session'])),worker.profile['protected'])
        require(all(type(audit.get(k))is int and audit[k]==value for k,value in actual.items()),
                'Prefix audit counts differ from the actual native scan')
        canonical=read(worker.root/('supervision-receipt-'+lease['id']+'.json'))
        require(safety.get('native_receipt')is True and not safety.get('local_verified')
                and not safety.get('lease_transition_pending')
                and {k:v for k,v in safety.items()if k not in ('native_receipt','parking_confirmation')}==canonical
                and canonical.get('lease')==lease['id']and canonical.get('job_session')==lease['job_session']
                and canonical.get('action')=='KEEP_PVE_GUARD'and canonical.get('cause')=='controller_finished'
                and type(canonical.get('time'))is int and canonical['time']>=raw['scan_ended_at']
                and isinstance(canonical.get('snapshot'),dict)and identity(canonical['snapshot'])==observed,
                'Prefix lacks its exact original native KEEP receipt')
        for frame in (canonical.get('snapshot'),safety.get('parking_confirmation'),final):
            require(isinstance(frame,dict),'Original prefix parking confirmation is unavailable')
            owned=frame.get('supervision_lease')or{}
            require(all(isinstance(p,list)and len(p)==3 and all(type(v)in(int,float)and math.isfinite(v)for v in p)
                    for p in (frame.get('pos'),owned.get('park_target'))),'Original audit parking pose is unavailable')
            require(frame.get('world_session')==observed['world_session']and frame.get('connected')is True
                    and frame.get('health')==20 and frame.get('manual_movement')is False
                    and all(frame.get(k)is True for k in ('flight','guard_armed','guard_pve_only'))
                    and not frame.get('under_water')and not(frame.get('safety_hold')or{}).get('active')
                    and all(owned.get(k)==v for k,v in (('kind','parking'),('id',lease['id']),('job_session',lease['job_session']),
                        ('world_session',observed['world_session']),('revision',audit.get('control_revision')),('remote_finish','guard')))
                    and frame.get('control_revision')==audit.get('control_revision')
                    and type(frame.get('time'))is int and frame['time']>=canonical['time']
                    and math.dist(frame['pos'],owned['park_target'])<=2,
                    'Original audit native PARK scope/protection differs')
        parked=final['supervision_lease'];native_state=final.get('supervision_safety')or{}
        require(final.get('phase')=='parking'and identity(final)==observed
                and parked.get('id')==audit.get('parking_lease')and parked.get('parked_at')==canonical['time']
                and all(native_state.get(k)==canonical[k]for k in ('lease','job_session','cause','action','time')),
                'Original audit final native parking/safety differs')
        last_final=final;raw_ids.append(raw['id'])
    require(book.get('dispatch_sequence')==last_work+len(audits),
            'A later dispatched/unknown audit exists outside this prefix')
    latest=worker.observer();current_identity(latest,observed);no_pending(worker.root,latest)
    require(all((latest.get('supervision_lease')or{}).get(k)==last_final['supervision_lease'].get(k)
                for k in ('id','job_session','world_session','revision'))
            and latest.get('control_revision')==last_final['control_revision']and stock(latest)==stock(last_final),
            'Current parked owner/inventory is not the last completed prefix audit')
    require(all(source.read_bytes()==raw for source,raw in captured.items())and worker.path.read_bytes()==current_book_bytes,
            'Original prefix evidence or current journal changed during validation')
    return {'schema':1,'campaign':campaign,'identity':observed,'prefix_path':str(path.resolve()),
            'prefix_sha256':hashlib.sha256(captured[path]).hexdigest(),'prefix_count':len(audits),
            'journal_at_validation_sha256':hashlib.sha256(current_book_bytes).hexdigest(),
            'wave_start':last_work+1,'last_actual_torch_at':last_torch,'torch_receipts':torch_records,
            'original_audit_requests':raw_ids,'new_scan_credit':0,'placement_credit':0,
            'coverage_complete':False,'final_audit_scope':'all_registered_regions',
            'evidence_sha256':{str(source.resolve()):hashlib.sha256(raw).hexdigest()for source,raw in captured.items()}}
