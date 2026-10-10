"""Archive an exact old pickup pre-navigation refusal; no game action or pickup credit."""
import hashlib
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json

OLD_SOURCE_SHA='d037108fef1f4dad8197e6889fe756656e3c5c8ba2fe70b0e09a7cd3ef6a1381'
DETAIL='Known UUID/stack or bounded center-hover context changed'


def reconcile(root,journal,out,control_dir,old_source):
    root=Path(root);journal=Path(journal);out=Path(out);control_dir=Path(control_dir)
    if out.exists():raise RuntimeError('Choose a new pickup refusal proof directory')
    if hashlib.sha256(Path(old_source).read_bytes()).hexdigest()!=OLD_SOURCE_SHA:
        raise RuntimeError('Original pickup pre-navigation source contract changed')
    raw=journal.read_bytes();book=json.loads(raw);pending=book.get('pending')or{}
    if pending.get('operation')!='await_loot' or book.get('last_wait',{}).get('detail')!=DETAIL:
        raise RuntimeError('Original exact pre-navigation refusal is absent')
    attempts=pending.get('pickup_attempts',{});candidates=[(u,a)for u,a in attempts.items()
        if a.get('stage')=='sent_once' and 'returned'not in a]
    if len(candidates)!=1:raise RuntimeError('One exact refused pickup required')
    uuid,attempt=candidates[0];drop=next((d for d in pending.get('owned_loot',[])if d['uuid']==uuid),None)
    if drop is None:raise RuntimeError('Original owned drop identity missing')
    events=[json.loads(line)for line in(control_dir/'events.jsonl').read_text().splitlines()]
    start=attempt['observation_time'];interval=[e for e in events if e['time']*1000>=start]
    park=next((e for e in interval if e['op']=='material_job_park'),None)
    if park is None:raise RuntimeError('Original interval has no known cleanup boundary')
    before_park=[e for e in interval if e['time']<=park['time']]
    if any(e['op']=='navigate'for e in before_park):raise RuntimeError('Pickup interval includes navigation; keep original attempt')
    snapshots=[e for e in before_park if e['op']=='snapshot']
    if len(snapshots)!=1:raise RuntimeError('One pre-navigation snapshot required')
    reply=json.loads((root/('reply-'+snapshots[0]['request_id']+'.json')).read_text())
    current=next((e for e in reply.get('entities',[])if e.get('uuid')==uuid),None)
    if (reply.get('world_session')!=book['world_session'] or current is None
            or current.get('id')!=drop['id'] or current.get('stack',{}).get('item')!=drop['item']
            or current.get('stack',{}).get('count')!=drop['count']
            or not 1<math.dist(current['pos'],drop['pos'])<=3):
        raise RuntimeError('Exact same falling UUID pre-navigation refusal not proven')
    if journal.read_bytes()!=raw:raise RuntimeError('Original pickup journal changed')
    out.mkdir(parents=True);(out/'original-harvest-before.json').write_bytes(raw)
    proof={'uuid':uuid,'world_session':book['world_session'],'no_navigation_sent':True,
           'original_attempt_not_done':True,'pickup_inventory_credit':0,'source_sha':OLD_SOURCE_SHA,
           'original_attempt':attempt,'original_drop':drop,'read_snapshot':reply,'events':before_park}
    path=out/'exact-pre-navigation-refusal.json';write_json(path,proof)
    book.setdefault('pickup_refusal_history',[]).append({'original_attempt':dict(attempt),'proof':str(path)})
    pending['pickup_attempts'][uuid]={**attempt,'stage':'refused_before_navigation','refusal_count':1,
                                     'pre_navigation_rejection_proof':str(path)}
    write_json(journal,book);return {k:proof[k]for k in('uuid','no_navigation_sent','original_attempt_not_done','pickup_inventory_credit')}
