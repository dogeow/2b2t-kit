"""Explicit new-connection observation binding for completed registered fields.

Old bytes/receipts are preserved. Only observations and connection binding are
new; no planting, harvesting, unlocking or reconnecting is issued here.
"""
from contextlib import ExitStack
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from farm_preparation import preparation_lock,assert_preparation_resolved
from idle_service import busy_reason,read,validate_profile
from kit_runtime.journal import write_json
from potato_farm import crop_descriptor,plan,_properties,_key,valid_entity_scope


def _verify(reply,scope,current,previous=None):
    layout=scope['layout'];crop=crop_descriptor(layout)
    if (reply.get('phase')!='done' or reply.get('connected') is not True
            or reply.get('world_session')!=current['world_session'] or reply.get('control_revision')!=current['control_revision']
            or not valid_entity_scope(reply.get('scan_entity_scope')) or reply.get('unloaded_chunks',0)
            or not isinstance(reply.get('scan_entities'),list) or reply['scan_entities']
            or type(reply.get('time'))is not int or reply['time']<= (previous['time'] if previous is not None else current['time'])
            or not isinstance(reply.get('blocks'),list)):
        raise RuntimeError('New connection field observation is incomplete or not two distinct native frames')
    rows={}
    for row in reply['blocks']:
        pos=row.get('pos')
        if (not isinstance(pos,list) or len(pos)!=3 or any(type(v)is not int for v in pos) or tuple(pos) in rows
                or not all(lo<=v<=hi for lo,v,hi in zip(layout['scan_min'],pos,layout['scan_max']))
                or type(row.get('fluid'))is not bool or type(row.get('block_entity'))is not bool or row['block_entity']):
            raise RuntimeError('New connection field block details are malformed or contain a protected container')
        rows[tuple(pos)]=row
    water=rows.get(tuple(layout['center']),{})
    if water.get('state')!='Block{minecraft:water}[level=0]' or water.get('fluid') is not True:raise RuntimeError('Original center water is not present')
    for pos in layout['cells']:
        soil=rows.get(tuple(pos),{});above=rows.get((pos[0],pos[1]+1,pos[2]),{})
        if (_properties(soil,'farmland','moisture',7) is None or soil.get('fluid') is not False
                or _properties(above,crop.block,'age',crop.age_max) is None or above.get('fluid') is not False):
            raise RuntimeError('Original complete field no longer has exact existing farmland and the same crop')
    return rows


def _replace_bytes(path,data):
    path=Path(path);temporary=path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def revalidate_fields(root,profile,*,acknowledge_existing_fields=False,observer=None,client_factory=None):
    if acknowledge_existing_fields is not True:
        raise ValueError('Explicit field-review acknowledgement is required: --acknowledge-existing-fields')
    root=Path(root).resolve();profile=validate_profile(profile)
    if not profile['plant_registries']:raise ValueError('Only explicitly registered planting fields may be revalidated')
    if observer is None:
        from live_snapshot import read_fresh
        observer=lambda:read_fresh(root)
    current=observer();reason=busy_reason(root,profile,current,hid_idle=1e9)
    if reason:raise RuntimeError('Field revalidation waits for real idle/safe state: '+reason)
    key=hashlib.sha256((profile['server']+'|'+profile['dimension']).encode()).hexdigest()[:20]
    home=root/'idle-services'/key;home.mkdir(parents=True,exist_ok=True)
    lock_path=home/'worker.lock';lock_path.touch(exist_ok=True)
    originals={};records=[];preparations=[]
    with ExitStack() as stack:
        lock=stack.enter_context(lock_path.open('rb'))
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:raise RuntimeError('Idle worker must be stopped before connection revalidation') from error
        book_path=home/'service.json'
        if book_path.exists() and read(book_path).get('pending'):raise RuntimeError('Unknown original idle action cannot be rebound')
        for selected in profile['plant_registries']:
            registry_path=Path(selected).resolve()
            if registry_path.name!='registry.json' or not registry_path.is_relative_to(root/'farms'):raise ValueError('Use the original local farm registry')
            registry=read(registry_path);scope=registry.get('scope') or {};layout=scope.get('layout') or {}
            request={'authorized':True,'center':layout.get('center'),'radius':layout.get('radius',2),'crop':layout.get('crop','potato')}
            field_key=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]
            if (scope.get('server')!=profile['server'] or scope.get('dimension')!=profile['dimension']
                    or plan(request)!=layout or registry_path.parent.name!=field_key):raise ValueError('Original field scope/hash is inconsistent')
            stack.enter_context(preparation_lock(root,current,request))
            # A completed previous preparation belongs to the old connection;
            # never adopt its uncertain water/soil/torch actions.
            prep=root/'farm-preparation'
            for prep_path in prep.glob('*/registry.json'):
                saved=read(prep_path);old_scope=saved.get('scope') or {}
                if old_scope.get('center')!=layout['center'] or old_scope.get('server')!=profile['server']:continue
                preparation_key=hashlib.sha256(json.dumps(old_scope,sort_keys=True).encode()).hexdigest()[:16]
                prior=Path(saved['directory']).resolve()/('farm-preparation-'+preparation_key+'.json');old=read(prior)
                if (old.get('scope')!=old_scope or old.get('world_session')!=saved.get('world_session')
                        or old.get('complete') is not True or old.get('pending') or old.get('cleanup_pending')):
                    raise RuntimeError('Only complete original preparation without unknown actions can be rebound')
                originals[prep_path]=prep_path.read_bytes();originals[prior]=prior.read_bytes()
                preparations.append((prep_path,saved,prior,old))
            crop=crop_descriptor(layout);plant_path=Path(registry['directory']).resolve()/(crop.journal_prefix+field_key+'.json')
            planted=read(plant_path)
            if (planted.get('scope')!=scope or planted.get('complete') is not True or planted.get('pending') or planted.get('cleanup_pending')
                    or any(planted.get('cells',{}).get(_key(pos),{}).get('planted') is not True for pos in layout['cells'])):
                raise RuntimeError('Only complete original planting with no unknown action can be observed on a new connection')
            originals[registry_path]=registry_path.read_bytes();originals[plant_path]=plant_path.read_bytes()
            active=registry_path.parent/'harvest-active.json'
            if active.exists():
                prior=Path(read(active)['journal']).resolve();harvest=read(prior)
                if harvest.get('pending') or harvest.get('cleanup_pending'):raise RuntimeError('Unknown original harvest cannot be rebound or bypassed')
                originals[active]=active.read_bytes();originals[prior]=prior.read_bytes()
            records.append((registry_path,registry,plant_path,planted,scope))
        destination=home/'connection-observations'/uuid.uuid4().hex;destination.mkdir(parents=True)
        if client_factory is None:
            from material_client import Client
            client_factory=lambda out:Client(root,out,current['server'],min_health=20)
        client=client_factory(destination/'read-only-client')
        evidence=[]
        for registry_path,registry,plant_path,planted,scope in records:
            layout=scope['layout'];frames=[]
            for _ in range(2):
                reply=client.request('scan',min=layout['scan_min'],max=layout['scan_max'],details=True)
                _verify(reply,scope,current,frames[-1] if frames else None);frames.append(reply)
            evidence.append({'field_key':registry_path.parent.name,'scope':scope,'old_world_session':planted.get('world_session'),
                'new_world_session':current['world_session'],'observation_times':[frame['time'] for frame in frames],
                'frames':frames,'scope_of_proof':'existing_complete_field_reobserved_not_new_planting_or_harvesting_receipt','server_verified':False})
        # Exact scan replies can precede the asynchronous status publication.
        # Observe the same completed read's later frame; never issue another
        # request or treat a foreign busy controller as our scan.
        after_time=max(frame['time'] for record in evidence for frame in record['frames'])
        deadline=time.monotonic()+3
        while True:
            latest=observer();reason=busy_reason(root,profile,latest,hid_idle=1e9)
            if latest.get('world_session')!=current['world_session'] or latest.get('control_revision')!=current['control_revision']:
                raise RuntimeError('World/control changed during read-only field observations')
            if reason is None and latest.get('time',0)>=after_time:break
            transient=('NATIVE_BUSY','OTHER_INPUT_OWNER:scan')
            own_lag=(latest.get('time',0)<after_time or reason in transient
                     and latest.get('last_request')==getattr(client,'last',None))
            if reason not in (None,*transient) or not own_lag or time.monotonic()>=deadline:
                raise RuntimeError('World/control/safety did not settle after the completed read-only scan: '+str(reason))
            time.sleep(.05)
        if any(path.read_bytes()!=data for path,data in originals.items()):raise RuntimeError('Original field evidence changed during review')
        manifest={'schema':1,'new_world_session':current['world_session'],'acknowledged':True,'committed':False,'game_mutations_sent':0,
            'originals':{},'evidence':evidence}
        for index,(path,data) in enumerate(originals.items()):
            backup=destination/('original-%03d-%s'%(index,path.name));_replace_bytes(backup,data)
            manifest['originals'][str(path)]={'copy':str(backup),'sha256':hashlib.sha256(data).hexdigest()}
        write_json(destination/'observation.json',manifest)
        changed=[]
        try:
            for registry_path,registry,plant_path,planted,scope in records:
                binding={'evidence':str(destination/'observation.json'),'current_world_session':current['world_session'],
                    'original_planting_world_session':planted.get('original_planting_world_session',planted.get('world_session')),
                    'read_only_revalidated':True,'new_planting_receipt':False}
                updated=deepcopy(planted);updated.update(world_session=current['world_session'],connection_binding=binding,
                    original_planting_world_session=binding['original_planting_world_session'])
                write_json(plant_path,updated);changed.append(plant_path)
                registered=deepcopy(registry);registered.update(world_session=current['world_session'],connection_binding=binding)
                write_json(registry_path,registered);changed.append(registry_path)
            for prep_path,registered,prior,prepared in preparations:
                binding={'evidence':str(destination/'observation.json'),'current_world_session':current['world_session'],
                         'original_preparation_world_session':prepared.get('original_preparation_world_session',prepared.get('world_session')),
                         'read_only_revalidated':True,'new_preparation_receipt':False}
                updated=deepcopy(prepared);updated.update(world_session=current['world_session'],connection_binding=binding,
                    original_preparation_world_session=binding['original_preparation_world_session'])
                write_json(prior,updated);changed.append(prior)
                updated=deepcopy(registered);updated.update(world_session=current['world_session'],connection_binding=binding)
                write_json(prep_path,updated);changed.append(prep_path)
            manifest['committed']=True;write_json(destination/'observation.json',manifest)
        except BaseException:
            for path in changed:_replace_bytes(path,originals[path])
            raise
        return {'phase':'revalidated','fields':len(records),'world_session':current['world_session'],'evidence':str(destination/'observation.json'),
            'game_mutations_sent':0,'worker_started':False,'ai_calls':0,'detail':'Completed fields were re-observed on this connection; old action bytes are archived, unknown actions were not adopted or replayed'}
