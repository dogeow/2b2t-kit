"""Build an exact prepared village stage through the existing projection printer."""
from collections import Counter
from pathlib import Path
import json,time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_jobs.projection_spatial_cache import native_content_hash

def unfinished_chest_pair(row,table,mismatches):
    """A witnessed single chest becomes the requested pair only by placing its missing partner."""
    from projection_completion import block_state
    try:
        block,goal=block_state(row['expected']);actual,live=block_state(row['actual'])
        pos=row['pos'];kind=goal['type'];facing=goal['facing']
    except (KeyError,ValueError,TypeError):return False
    if (row.get('kind')!='state_only' or block!=actual or block not in ('minecraft:chest','minecraft:trapped_chest')
            or kind not in ('left','right')or live.get('type')!='single'
            or {k:v for k,v in goal.items()if k!='type'}!={k:v for k,v in live.items()if k!='type'}):return False
    clockwise={'north':(1,0),'east':(0,1),'south':(-1,0),'west':(0,-1)}
    if facing not in clockwise:return False
    dx,dz=clockwise[facing];sign=1 if kind=='left'else-1;partner=[pos[0]+sign*dx,pos[1],pos[2]+sign*dz]
    wanted=next((r for r in table['expected']if r['pos']==partner),None)
    missing=next((r for r in mismatches if r['pos']==partner),None)
    if not wanted or not missing or missing.get('kind')!='missing'or missing.get('actual')!='Block{minecraft:air}':return False
    try:other,props=block_state(wanted['state'])
    except (KeyError,ValueError,TypeError):return False
    return other==block and props=={**goal,'type':'right'if kind=='left'else'left'}

def floor_work_pose(positions):
    """Validated open-plane stance: centre the targets, above their top surface.

    A lower stance stalled on the cell directly beneath the actor. Callers
    still use the native collision-aware navigator; this never moves a player.
    """
    if(not positions or any(not isinstance(p,list)or len(p)!=3 or any(type(n)is not int for n in p)for p in positions)
            or len({p[1]for p in positions})!=1 or len({tuple(p)for p in positions})!=len(positions)):
        raise ValueError('One distinct horizontal floor layer is required')
    return [sum(p[0]+.5 for p in positions)/len(positions),positions[0][1]+2.2,
            sum(p[2]+.5 for p in positions)/len(positions)]

def verify(model,table):
    rows=model.get('expected');planned=table.get('expected')
    if(model.get('model_schema')!=1 or not model.get('loaded_chunks_verified')or not model.get('loaded_server_chunks_verified')
            or not isinstance(rows,list)or not isinstance(planned,list)or not planned
            or len(rows)!=len(planned)or model.get('total')!=len(planned)
            or model.get('bounds')!=table.get('bounds')
            or {tuple(r['pos']):(r['state'],r['item'])for r in rows}!={tuple(r['pos']):(r['state'],r['item'])for r in planned}
            or len({tuple(r['pos'])for r in rows})!=len(rows)
            or native_content_hash(rows)!=model.get('content_hash')):
        raise RuntimeError('Current complete projection differs from the exact prepared village stage; no building started')
    return model['placement_key']

def build(c,table_path,out,checkpoint,label):
    from goal_workflow import audit,build_phase
    project_progress=getattr(c,'job_progress',None)
    table=json.loads(Path(table_path).read_text());checkpoint()
    received=c.request('projection_model')
    if received.get('phase')not in(None,'done')or'projection_model'not in received:
        raise RuntimeError('Complete native projection model read is unavailable')
    model=received['projection_model'];key=verify(model,table)
    out=Path(out);write_json(out/'native-model.json',model)
    before=audit(c,'village-stage-before-'+str(time.time_ns()))
    if before['placement_key']!=key or before['total']!=len(table['expected']):raise RuntimeError('Prepared stage audit changed')
    missing=before.get('mismatches',[])
    if len(missing)!=before['total']-before['matched']or any(r['kind']!='missing'and not unfinished_chest_pair(r,table,missing)for r in missing):
        raise RuntimeError('Village stage has a non-air obstacle or incomplete audit; no replacement or mining')
    materials={tuple(r['pos']):r['item']for r in table['expected']}
    needed=Counter(materials[tuple(r['pos'])]for r in missing if r['kind']=='missing');initial=inventory_counts(checkpoint())
    if any(initial[i]<n for i,n in needed.items()):raise RuntimeError('Actual carried village stage materials are incomplete')
    book={'world_session':c.world,'placement_key':key,'before':before,'inventory_before':dict(initial),'needed':dict(needed),'complete':False}
    write_json(out/'stage.json',book)
    c.start_progress('村民交易中心·'+label,before['total'],done=before['matched'])
    if needed:c.checked('select_item',item=needed.most_common(1)[0][0])
    for attempt in range(3):
        result=build_phase(c,key,seconds=70,stall_seconds=10,background=True,max_station_repositions=0,air_seed_limit=1)
        book.setdefault('passes',[]).append(result);write_json(out/'stage.json',book)
        if result['matched']==result['total']:break
        if attempt and result['matched']<=book['passes'][-2]['matched']:raise RuntimeError('Same native printer stage made no new progress; retain current evidence')
    if result['matched']!=len(table['expected']):raise RuntimeError('Village stage is physically incomplete')
    observed=[]
    for index in range(2):
        checkpoint();fresh=audit(c,'village-stage-final-'+str(time.time_ns()))
        if(fresh.get('placement_key')!=key or fresh.get('total')!=len(table['expected'])or fresh.get('matched')!=fresh['total']
                or fresh.get('mismatches')or not fresh.get('loaded_server_chunks_verified')):
            raise RuntimeError('Whole village stage lacks complete current physical verification')
        observed.append(fresh);time.sleep(.2)
    after=inventory_counts(checkpoint())
    if any(initial[i]-after[i]!=n for i,n in needed.items()):raise RuntimeError('Placed village stage and actual carried material debit differ')
    book.update(complete=True,after=observed,inventory_after=dict(after));write_json(out/'stage.json',book)
    if project_progress is not None:
        c.job_progress=project_progress
        c.set_progress(phase='本阶段已核验，继续交易中心')
    return {'complete':True,'matched':result['matched'],'total':result['total'],'material_debit':dict(needed),'proof':str((out/'stage.json').resolve())}
