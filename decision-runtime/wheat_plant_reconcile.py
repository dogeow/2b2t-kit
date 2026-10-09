"""Reconcile only a pinned host's exact pre-use wheat planting rejection."""
import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from kit_runtime.journal import write_json
from potato_farm import _counts,_key

REJECTION='Target interaction face is occluded or out of reach'
HOST='2026.10.10.1'
HOST_CLASS_SHA='00f03248aa8a3eeec90afc3ac28a854e44867214ff083685540506479a52943e'


def contract(root):
    game=Path(root).resolve().parents[2]
    jars=list((game/'mods').glob('twob2tkit-*.jar'))
    if len(jars)!=1:raise RuntimeError('Unique current Kit host required')
    with ZipFile(jars[0])as z:
        version=json.loads(z.read('fabric.mod.json'))['version']
        code=z.read('dev/twob2tkit/automation/AutomationBridge.class')
    digest=hashlib.sha256(code).hexdigest()
    if version!=HOST or digest!=HOST_CLASS_SHA or code.count(REJECTION.encode())!=1:
        raise RuntimeError('Exact pre-use rejection host contract is not verified')
    return {'kit_version':version,'class_sha256':digest,'rejection_before_use_item_on':True}


def prove(book,reply,event,current,host):
    pending=book.get('pending')or{};native=pending.get('receipt')or{};pos=pending.get('pos')
    harvest=book.get('cells',{}).get(_key(pos),{}).get('harvest',{})if isinstance(pos,list)else{}
    if (host.get('kit_version')!=HOST or host.get('class_sha256')!=HOST_CLASS_SHA
            or pending.get('operation')!='plant' or native.get('phase')!='error' or native.get('detail')!=REJECTION
            or not harvest.get('native_mining_confirmed') or harvest.get('remaining_count')!=0
            or reply.get('id')!=native.get('id') or reply.get('phase')!='error' or reply.get('detail')!=REJECTION
            or reply.get('time')!=native.get('time')
            or reply.get('kit_version')!=HOST or reply.get('world_session')!=book.get('world_session')
            or reply.get('server')!=event.get('server',reply.get('server'))
            or reply.get('dimension')!='minecraft:overworld'
            or event.get('request_id')!=reply['id'] or event.get('op')!='interact'
            or event.get('phase')!='error' or event.get('detail')!=REJECTION
            or event.get('params',{}).get('pos')!=pos or event.get('params',{}).get('face')!='up'
            or event.get('params',{}).get('expected_hand')!='minecraft:wheat_seeds'
            or event.get('params',{}).get('expected_state')!=pending.get('expected_state')
            or event.get('inventory_delta')!={} or event.get('revision_before')!=event.get('revision_after')
            or event.get('revision_after')!=reply.get('control_revision')
            or event.get('position_before')!=event.get('position_after')
            or reply.get('inventory')!=pending.get('before_inventory') or reply.get('hand')!=pending.get('hand_before')
            or dict(_counts(current))!=pending.get('before_counts') or current.get('world_session')!=book.get('world_session')
            or current.get('control_revision')!=reply.get('control_revision')
            or current.get('recent_hurt_at')!=book.get('recent_hurt_at')
            or current.get('health')!=20 or current.get('manual_movement')or current.get('screen')
            or (current.get('supervision_lease')or{}).get('job_session')!=event['params'].get('task_session')):
        raise RuntimeError('Exact rejected planting and unchanged current inventory/owner are not proven')
    return {'outcome':'rejected_without_use','request_id':reply['id'],'world_session':book['world_session'],
            'original_attempt_not_done':True,'seed_debit':0,'host_contract':host,'pos':pos}


def reconcile(c,journal,out,control_dir=None):
    journal=Path(journal);out=Path(out)
    if out.exists():raise RuntimeError('Choose a new proof directory; no archive overwritten')
    book=json.loads(journal.read_text());pending=book.get('pending')or{};rid=(pending.get('receipt')or{}).get('id')
    reply=json.loads((c.root/('reply-'+str(rid)+'.json')).read_text())
    directory=Path(control_dir)if control_dir is not None else c.out
    events=[json.loads(line)for line in(directory/'events.jsonl').read_text().splitlines()]
    matches=[e for e in events if e.get('request_id')==rid]
    if len(matches)!=1:raise RuntimeError('Single original event required')
    proof=prove(book,reply,matches[0],c.status(),contract(c.root))
    out.mkdir(parents=True);(out/'original-harvest-journal-before.json').write_bytes(journal.read_bytes())
    write_json(out/'exact-pre-use-rejection-proof.json',{'proof':proof,'reply':reply,'event':matches[0]})
    book.setdefault('rejected_plant_history',[]).append({'original_pending':copy.deepcopy(pending),'proof':str(out/'exact-pre-use-rejection-proof.json')})
    book['pending']={'operation':'await_replant','pos':pending['pos'],'pre_drop_ids':pending.get('pre_drop_ids',[]),
                     'prior_plant_rejected_without_use':str(out/'exact-pre-use-rejection-proof.json')}
    write_json(journal,book)
    return proof
