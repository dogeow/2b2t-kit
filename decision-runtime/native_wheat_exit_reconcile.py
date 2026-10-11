"""Resolve only an acknowledged crop visit's dry post-walk coasting, with no game actions."""
import copy
import hashlib
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json
from material_jobs.native_wheat import validate_receipt, dry_footprint
from material_plan import inventory_counts
from potato_farm import FarmWait, _properties


def reconcile(journal, events_file, out):
    journal=Path(journal);events_file=Path(events_file);out=Path(out)
    raw=journal.read_bytes();book=json.loads(raw);home=journal.parent
    pending=book.get('pending')or{};layout=book['scope'];world=book['world_session']
    if (book.get('complete')is not False or pending.get('operation')!='registered_farmland_exit_step'
            or book.get('controller')!='Kit.AutoPlanter'):
        raise FarmWait('WAIT_RECONCILE','Only the original post-crop farmland step may be resolved')
    native=json.loads((home/'native-wheat-receipt.json').read_text())
    before=book['inventory_before'].get('minecraft:wheat',0)
    counts=validate_receipt(native,book['cells'],before,world)
    lease=native.get('supervision_lease')or{};task=lease.get('job_session')
    if not task or lease.get('world_session')!=world:
        raise FarmWait('WAIT_RECONCILE','Original native crop owner is unproved')
    volume=math.prod(b-a+1 for a,b in zip(layout['scan_min'],layout['scan_max']))
    last=native['time'];frames=[]
    for n in range(2):
        frame=json.loads((home/('native-wheat-final-%d.json'%n)).read_text());frames.append(frame)
        rows={tuple(r['pos']):r for r in frame['blocks']}
        if (frame.get('phase')!='done' or frame.get('world_session')!=world
                or frame.get('scan_cells_read')!=volume or frame.get('scan_total_cells')!=volume
                or frame.get('scan_start_revision')!=native['control_revision']
                or frame.get('scan_end_revision')!=native['control_revision'] or frame.get('unloaded_chunks',0)
                or frame.get('time',0)<=last or inventory_counts(frame)!=counts
                or (frame.get('supervision_lease')or{}).get('job_session')!=task
                or (frame.get('supervision_lease')or{}).get('id')!=lease.get('id')
                or any(_properties(rows.get((p[0],p[1]+1,p[2]),{}),'wheat','age',7)is None
                       or _properties(rows.get(tuple(p),{}),'farmland','moisture',7)is None
                       for p in book['cells'])):
            raise FarmWait('WAIT_RECONCILE','Original native final crop/inventory frames are unproved')
        last=frame['time']
    exit=json.loads((home/'farmland-exit.json').read_text());target=pending['target']
    if exit.get('world_session')!=world or exit.get('target')!=target or exit.get('inventory_before')!=dict(counts):
        raise FarmWait('WAIT_RECONCILE','Original exit intent is unproved')
    events=[json.loads(line)for line in events_file.read_text().splitlines()if line]
    original=[n for n,e in enumerate(events)if e.get('request_id')==native['id']]
    if len(original)!=1:raise FarmWait('WAIT_RECONCILE','Original native crop event is absent or duplicated')
    later=events[original[0]+1:];walks=[(n,e)for n,e in enumerate(later)
        if e.get('op')=='walk' and e.get('params',{}).get('target')==target]
    if len(walks)!=1:raise FarmWait('WAIT_RECONCILE','Original exit walk is absent or repeated')
    index,walk=walks[0];after=later[index+1:index+2]
    def owned(e):
        return (e.get('world_session')==world and e.get('params',{}).get('task_session')==task
                and e.get('health',0)>=19 and e.get('inventory_delta')=={})
    if (walk.get('phase')!='done' or walk.get('params',{}).get('arrival')!=.15 or not owned(walk)
            or walk.get('time',0)*1000<=last or math.dist(walk['pos'],target)>.15
            or len(after)!=1 or after[0].get('op')not in ('scan','snapshot','settle')
            or after[0].get('phase')not in ('done',None) or not owned(after[0])
            or after[0].get('time',0)<=walk.get('time',0)
            or not dry_footprint(after[0].get('pos'),layout,frames[-1])):
        raise FarmWait('WAIT_RECONCILE','Exact acknowledged walk and later dry footprint are unproved')
    digest=hashlib.sha256(raw).hexdigest();out.mkdir(parents=True,exist_ok=False)
    proof={'world_session':world,'original_journal':str(journal.resolve()),'original_sha256':digest,
           'original_unmodified':True,'crop_request':native['id'],'walk_request':walk['request_id'],
           'dry_coasting_pos':after[0]['pos'],'native_replanted_cells':len(book['cells']),
           'historical_grain_gain':counts['minecraft:wheat']-before,'new_game_commands':0}
    write_json(out/'proof.json',proof)
    resolved=copy.deepcopy(book);resolved.update(complete=True,pending=None,
        inventory_after=dict(counts),inventory_credit=counts['minecraft:wheat']-before,
        server_cells_confirmed=True,reconciled_from=proof)
    copy_path=out/'resolved-native-wheat-batch.json';write_json(copy_path,resolved)
    if journal.read_bytes()!=raw:raise FarmWait('WAIT_RECONCILE','Original source changed during read-only reconciliation')
    return copy_path,proof
