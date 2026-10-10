"""Explicit fresh restoration of a completed original field; preserve its history."""
import hashlib
import json
from pathlib import Path

from farm_preparation import _identity, _scope
from kit_runtime.journal import write_json
from potato_farm import plan
from terminal_confirmation import verified


def create_intent(root, original_registry, state, out, *, water_source):
    root=Path(root).resolve();original_registry=Path(original_registry).resolve();out=Path(out).resolve()
    if original_registry.parent.parent!=root/'farms' or original_registry.name!='registry.json':
        raise ValueError('Use the original registered field')
    original=json.loads(original_registry.read_text());scope=original['scope'];layout=scope['layout']
    request={'authorized':True,'center':layout['center'],'radius':layout['radius'],
             'crop':layout['crop'],'bonemeal':False}
    if (layout.get('crop')!='wheat' or plan(request)!=layout
            or scope['server']!=state['server'].removesuffix(':25565')
            or scope['dimension']!=state['dimension'] or not state['connected']):
        raise ValueError('Original layout or current world scope differs')
    key=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]
    if original_registry.parent.name!=key:raise ValueError('Original registration identity differs')
    old_plant=Path(original['directory'])/('wheat-farm-'+key+'.json')
    planting=json.loads(old_plant.read_text())
    prep_scope=_scope(state,request);prep_key=_identity({k:v for k,v in prep_scope.items()if k!='radius'})
    prep_registry=root/'farm-preparation'/prep_key/'registry.json';old_prep_registry=json.loads(prep_registry.read_text())
    old_prep=Path(old_prep_registry['directory'])/('farm-preparation-'+_identity(prep_scope)+'.json')
    preparation=json.loads(old_prep.read_text())
    for book in (planting,preparation):
        if book.get('complete')is not True or book.get('pending')or book.get('cleanup_pending'):
            raise ValueError('Original preparation or planting unresolved; no restoration bypass')
    if planting.get('scope')!=scope or preparation.get('scope')!=prep_scope:
        raise ValueError('Original journal scope differs')
    out.mkdir(parents=True,exist_ok=False);archive=out/'original';archive.mkdir()
    sources={'plant-registry.json':original_registry,'plant-journal.json':old_plant,
             'preparation-registry.json':prep_registry,'preparation-journal.json':old_prep}
    for pointer in ('harvest-active.json','reseed-active.json'):
        path=original_registry.parent/pointer
        if path.exists():sources[pointer]=path
    hashes={}
    for name,path in sources.items():
        data=path.read_bytes();(archive/name).write_bytes(data);hashes[str(path)]=hashlib.sha256(data).hexdigest()
    proof={'schema':1,'kind':'explicit_current_restoration_of_completed_original_field',
           'original_scope':scope,'current_world_session':state['world_session'],
           'old_journal_hashes':hashes,'old_harvest_actions_replayed':False,
           'source_registry':str(original_registry),'complete':False}
    write_json(out/'restoration-intent.json',proof)
    prep_dir=out/'preparation';prep_dir.mkdir()
    write_json(prep_registry,{'schema':1,'scope':prep_scope,'world_session':state['world_session'],
        'water_source':water_source,'directory':str(prep_dir),'restoration_intent':str(out/'restoration-intent.json')})
    return {**request,'water_source':water_source},prep_dir


def bind_completed_planting(root, original_registry, state, out):
    """Advance the current planting pointer only after preparation is complete."""
    root=Path(root);original_registry=Path(original_registry);out=Path(out)
    intent=json.loads((out/'restoration-intent.json').read_text());scope=intent['original_scope']
    prep_scope=_scope(state,{'authorized':True,'center':scope['layout']['center'],'radius':scope['layout']['radius']})
    journal=out/'preparation'/('farm-preparation-'+_identity(prep_scope)+'.json')
    if not journal.is_file():raise ValueError('Fresh preparation journal is missing')
    book=json.loads(journal.read_text())
    if (book.get('complete')is not True or book.get('pending')or book.get('cleanup_pending')
            or book.get('world_session')!=state['world_session']):raise ValueError('Fresh preparation must finish before planting')
    directory=out/'planting';directory.mkdir(exist_ok=True)
    write_json(original_registry,{'scope':scope,'world_session':state['world_session'],
        'directory':str(directory.resolve()),'restoration_intent':str((out/'restoration-intent.json').resolve())})
    return directory


def reconcile_confirmed_center_mine(journal, state, scans):
    """Accept an original server ACK plus two later empty, entity-free frames."""
    from farm_preparation import plan as preparation_plan,_rows
    journal=Path(journal);raw=journal.read_bytes();book=json.loads(raw);pending=book.get('pending')or{}
    reply=pending.get('receipt')or{};params=pending.get('params')or{};scope=book.get('scope')or{}
    if (pending.get('op')!='mine_block' or pending.get('stage')!='returned_pending_proof'
            or book.get('world_session')!=state.get('world_session')
            or params.get('pos')!=scope.get('center')
            or not verified('mine_block',reply,state['world_session'],reply.get('id'),params)
            or len(scans)!=2):raise ValueError('Original center mining proof is incomplete; no replay')
    layout=preparation_plan({'authorized':True,'center':scope['center'],'radius':scope['radius']})
    times=[]
    for scan in scans:
        rows=_rows(scan,layout['scan_min'],layout['scan_max'])
        if (scan.get('world_session')!=state['world_session'] or scan.get('control_revision')!=state['control_revision']
                or scan['time']<=reply.get('time',0) or tuple(scope['center'])in rows):
            raise ValueError('Current center is not independently proved empty')
        times.append(scan['time'])
    if times[1]<=times[0]:raise ValueError('Distinct current center observations required')
    archive=journal.parent/'reconciliation';archive.mkdir(exist_ok=True)
    digest=hashlib.sha256(raw).hexdigest();(archive/('before-'+digest[:16]+'.json')).write_bytes(raw)
    proof={'kind':'original_server_confirmed_center_mine_current_empty_frames','world_session':state['world_session'],
           'request_id':reply['id'],'center':scope['center'],'observed_times':times,
           'original_pending_sha256':digest,'new_mining_sent':False}
    write_json(archive/'center-mine-proof.json',proof)
    book['actions'].append({**pending,'independent_reconciliation':proof});book['pending']=None
    write_json(journal,book);return proof
