"""Prove an already dispatched wheat reseed from its event and fresh reads only."""
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json
from potato_farm import _counts, _key, _properties
from material_jobs.protocol import server_key


def complete_inventory(rows):
    return (isinstance(rows,list) and len(rows)==43
            and {r.get('slot')for r in rows if isinstance(r,dict)}==set(range(43)))


def prove(book, events, frames, low, high):
    pending=book.get('pending')or{};pos=pending.get('pos');receipt=pending.get('receipt')or{}
    layout=book.get('scope',{}).get('layout',{});seed='minecraft:wheat_seeds'
    if (pending.get('operation')!='plant' or receipt.get('phase')!='done'
            or not isinstance(receipt.get('id'),str)or not receipt['id']
            or type(receipt.get('time'))is not int or receipt['time']<=0
            or not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos)
            or layout.get('crop')!='wheat' or pos not in layout.get('harvest_cells',[])
            or not complete_inventory(pending.get('before_inventory'))
            or _counts({'inventory':pending['before_inventory']})!=Counter(pending.get('before_counts')or{})
            or (pending.get('hand_before')or{}).get('item')!=seed
            or (pending.get('hand_before')or{}).get('count',0)<1):
        raise RuntimeError('One original done wheat planting intent is required')
    harvest=(book.get('cells',{}).get(_key(pos),{}).get('harvest')or{})
    if harvest.get('native_mining_confirmed')is not True or harvest.get('remaining_count')!=0:
        raise RuntimeError('Original harvested crop and loot must already be confirmed')
    matches=[e for e in events if e.get('request_id')==receipt.get('id')]
    if len(matches)!=1:raise RuntimeError('Original planting must have exactly one native event')
    event=matches[0];params=event.get('params')or{}
    original_position=event.get('position_before')
    if (event.get('op')!='interact' or event.get('phase')!='done'
            or event.get('world_session')!=book.get('world_session')
            or params.get('pos')!=pos or params.get('face')!='up'
            or params.get('expected_hand')!=seed
            or params.get('expected_state')!=pending.get('expected_state')
            or event.get('inventory_delta')!={seed:-1}
            or type(event.get('revision_before'))is not int
            or event.get('revision_before')!=event.get('revision_after')
            or not isinstance(original_position,list)or len(original_position)!=3
            or any(type(v)not in (int,float)or not math.isfinite(v)for v in original_position)
            or event.get('position_before')!=event.get('position_after')):
        raise RuntimeError('Original exact stationary planting and one-seed debit are not proven')
    expected=Counter(pending.get('before_counts')or{});expected[seed]-=1
    if expected[seed]<4 or len(frames)!=2:
        raise RuntimeError('Seed reserve and two fresh frames are required')
    if (not isinstance(low,list)or not isinstance(high,list)or len(low)!=3 or len(high)!=3
            or any(type(v)is not int for v in low+high)or any(a>b for a,b in zip(low,high))
            or not all(low[i]<=pos[i]<=high[i]for i in range(3)) or high[1]<pos[1]+1):
        raise RuntimeError('Complete bounds must contain the original soil and crop')
    volume=math.prod(b-a+1 for a,b in zip(low,high));times=[];ages=[];revision=None
    for frame in frames:
        current_revision=frame.get('control_revision')
        if (frame.get('phase')!='done' or frame.get('world_session')!=book.get('world_session')
                or server_key(frame.get('server'))!=book.get('scope',{}).get('server')
                or frame.get('dimension')!='minecraft:overworld' or frame.get('manual_movement')
                or frame.get('scan_cells_read')!=volume or frame.get('scan_total_cells')!=volume
                or type(current_revision)is not int or frame.get('scan_start_revision')!=current_revision
                or frame.get('scan_end_revision')!=current_revision
                or revision is not None and current_revision!=revision
                or type(frame.get('time'))is not int or frame['time']<=receipt.get('time',0)
                or times and frame['time']<=times[-1] or not complete_inventory(frame.get('inventory'))
                or _counts(frame)!=expected):
            raise RuntimeError('Two distinct coherent current frames and exact inventory are required')
        rows={}
        for row in frame.get('blocks',[]):
            p=row.get('pos')
            if (not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)
                    or tuple(p)in rows or not all(low[i]<=p[i]<=high[i]for i in range(3))):
                raise RuntimeError('Native crop frame contains invalid or duplicate cells')
            rows[tuple(p)]=row
        soil=rows.get(tuple(pos),{});crop=rows.get((pos[0],pos[1]+1,pos[2]),{})
        age=_properties(crop,'wheat','age',7)
        if (_properties(soil,'farmland','moisture',7)is None or age is None
                or any(row.get('fluid')is not False or row.get('block_entity')is not False for row in (soil,crop))
                or ages and age<ages[-1]):
            raise RuntimeError('Actual original farmland and non-regressing wheat are required')
        revision=current_revision;times.append(frame['time']);ages.append(age)
    return {'outcome':'plant_confirmed_by_original_event_and_two_current_frames',
            'request_id':receipt['id'],'pos':pos,'world_session':book['world_session'],
            'seed_debit':1,'observed_times':times,'observed_ages':ages,
            'after_counts':dict(expected),'new_planting_use_sent':False,'server_verified':False}


def reconcile(journal, events_path, frame_paths, out, *, low, high):
    journal=Path(journal);out=Path(out)
    if out.exists():raise RuntimeError('A new reconciliation directory is required')
    raw=journal.read_bytes();book=json.loads(raw)
    event_raw=Path(events_path).read_bytes();events=[json.loads(x)for x in event_raw.decode().splitlines()if x.strip()]
    frames=[json.loads(Path(p).read_text())for p in frame_paths]
    proof=prove(book,events,frames,low,high)
    if journal.read_bytes()!=raw:raise RuntimeError('Original planting journal changed during proof')
    out.mkdir();(out/'original-harvest-before.json').write_bytes(raw)
    proof.update(original_journal_sha256=hashlib.sha256(raw).hexdigest(),
                 original_events=str(events_path),events_sha256=hashlib.sha256(event_raw).hexdigest(),
                 frames=[{'path':str(p),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()}for p in frame_paths])
    write_json(out/'proof.json',proof)
    pending=book['pending'];record=book['cells'][_key(pending['pos'])]
    record['plant']={**copy.deepcopy(pending),'observed_times':proof['observed_times'],
        'after_counts':proof['after_counts'],'read_only_reconciliation':str(out/'proof.json')}
    record['replanted']=True;book['pending']=None
    selected={_key(p)for p in book['scope']['layout']['harvest_cells']}
    if selected==set(book['cells'])and all(book['cells'][k].get('replanted')is True for k in selected):
        book['complete']=True;book['seeds_after']=proof['after_counts']['minecraft:wheat_seeds']
        book['wheat_after']=proof['after_counts'].get('minecraft:wheat',0)
    write_json(journal,book)
    return proof
