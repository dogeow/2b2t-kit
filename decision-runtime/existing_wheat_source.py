"""Register observed user wheat cells without claiming any Kit planting action."""
import hashlib
import json
from pathlib import Path

from kit_runtime.journal import write_json
from potato_farm import _counts,_key,_properties,plan,survey_rows
from material_jobs.protocol import server_key


def observed_request(frames,center,radius):
    if len(frames)!=2:raise ValueError('Two current complete field frames are required')
    x,y,z=center;lo=[x-radius-1,y-1,z-radius-1];hi=[x+radius+1,y+2,z+radius+1]
    volume=(2*radius+3)**2*4;world=frames[0].get('world_session');last=None;revision=None
    selected=None;protected=None;counts=_counts(frames[0])
    for frame in frames:
        if (frame.get('phase')!='done'or not world or frame.get('world_session')!=world
                or frame.get('scan_cells_read')!=volume or frame.get('scan_total_cells')!=volume
                or type(frame.get('control_revision'))is not int
                or frame.get('scan_start_revision')!=frame['control_revision']
                or frame.get('scan_end_revision')!=frame['control_revision']
                or revision is not None and frame['control_revision']!=revision
                or type(frame.get('time'))is not int or last is not None and frame['time']<=last
                or frame.get('manual_movement')or _counts(frame)!=counts):
            raise ValueError('Current coherent field and unchanged inventory are required')
        rows={}
        for row in frame.get('blocks',[]):
            p=row.get('pos')
            if (not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)
                    or tuple(p)in rows or not all(lo[i]<=p[i]<=hi[i]for i in range(3))):
                raise ValueError('Field source contains invalid or duplicate native cells')
            rows[tuple(p)]=row
        cells=sorted([[p[0],y,p[2]]for p,r in rows.items()if p[1]==y+1
            and abs(p[0]-x)<=radius and abs(p[2]-z)<=radius and(p[0],p[2])!=(x,z)
            and _properties(r,'wheat','age',7)is not None
            and _properties(rows.get((p[0],y,p[2]),{}),'farmland','moisture',7)is not None])
        obstacles=sorted([{k:r[k]for k in ('pos','state','fluid','block_entity')}
            for r in rows.values()if(r.get('fluid')or r.get('block_entity'))and r['pos']!=center],key=lambda r:r['pos'])
        if selected is not None and(cells!=selected or obstacles!=protected):
            raise ValueError('Existing crop selection or protected obstacles changed')
        selected,protected=cells,obstacles;last=frame['time'];revision=frame['control_revision']
    request={'authorized':True,'crop':'wheat','center':center,'radius':radius,
        'existing_source':{'schema':1,'kind':'observed_existing_wheat','cells':selected,
                           'protected_obstacles':protected}}
    layout=plan(request);records={_key(p):{'planted':True}for p in layout['cells']}
    for frame in frames:survey_rows(frame,layout,records)
    return request


def register(root,frames,center,radius,out):
    root=Path(root);out=Path(out)
    if out.exists():raise ValueError('Use a new existing-source observation directory')
    request=observed_request(frames,center,radius);layout=plan(request)
    server=server_key(frames[0].get('server'));dimension=frames[0].get('dimension')
    if not server or dimension!='minecraft:overworld':raise ValueError('Current overworld server required')
    scope={'server':server,'dimension':dimension,'layout':layout}
    key=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]
    registry=root/'farms'/key/'registry.json'
    if registry.exists():raise ValueError('Existing registry must be reused; never replace it here')
    out.mkdir(parents=True);out=out.resolve();times=[f['time']for f in frames]
    for i,f in enumerate(frames):write_json(out/f'frame-{i}.json',f)
    counts=_counts(frames[-1]);book={'schema':1,'kind':'observed_existing_wheat_source',
        'scope':scope,'world_session':frames[0]['world_session'],
        'cells':{_key(p):{'planted':True,'observed_existing':True,'observed_times':times}for p in layout['cells']},
        'pending':None,'complete':True,'completion_scope':'read_only_observation_of_existing_user_crops',
        'new_planting_uses':0,'new_seed_debit':0,'grain_inventory_credit':0,
        'seeds_before':counts['minecraft:wheat_seeds'],'seeds_after':counts['minecraft:wheat_seeds'],
        'server_verified':False}
    write_json(out/f'wheat-farm-{key}.json',book)
    registry.parent.mkdir(parents=True,exist_ok=True)
    write_json(registry,{'schema':1,'scope':scope,'world_session':frames[0]['world_session'],
        'directory':str(out),'origin':'observed_existing_user_field','preferred_material_source':True})
    return {'phase':'registered','registry':str(registry),'key':key,'cells':len(layout['cells']),
            'new_planting_uses':0,'new_seed_debit':0,'grain_inventory_credit':0,'request':request}
