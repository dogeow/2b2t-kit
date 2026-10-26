"""Explicit client-loaded ground threat lens; never infer safety from status.entities.

Entity samples are from the end of one complete bounded native scan. This is
not whole-world absence, an atomic block snapshot, or future safety proof.
"""
import math

ENTITY_SCOPE='current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd'

def bounds(foot):
    if not isinstance(foot,list)or len(foot)!=3 or any(type(n)not in(int,float)or not math.isfinite(n)for n in foot):raise ValueError('Finite planned feet required')
    x,y,z=map(math.floor,foot)
    return [x-24,y-4,z-24],[x+24,y+12,z+24]

def assess(request,reply,foot,*,world,task,revision,now_ms,max_age_ms=2000):
    low,high=bounds(foot);needed=math.prod(b-a+1 for a,b in zip(low,high))
    try:
        supplied_low=request['min'];supplied_high=request['max'];total=math.prod(b-a+1 for a,b in zip(supplied_low,supplied_high))
        valid=(isinstance(world,str)and bool(world)and isinstance(task,str)and bool(task)and type(revision)is int
            and request.get('id')==reply.get('id')and bool(request.get('id'))
            and request.get('world_session')==world and request.get('task_session')==task and request.get('expected_revision')==revision
            and request.get('op')=='scan'and request.get('details')is True
            and isinstance(supplied_low,list)and isinstance(supplied_high,list)and len(supplied_low)==len(supplied_high)==3
            and all(type(n)is int for n in supplied_low+supplied_high)
            and all(a<=b for a,b in zip(supplied_low,low))and all(a>=b for a,b in zip(supplied_high,high))
            and needed<=total<=50000 and reply['phase']=='done'and reply['world_session']==world
            and reply['scan_start_revision']==reply['scan_end_revision']==revision
            and reply['scan_cells_read']==reply['scan_total_cells']==total
            and reply['scan_entity_scope']==ENTITY_SCOPE and isinstance(reply['scan_entities'],list)
            and type(reply['scan_ended_at'])is int and 0<=now_ms-reply['scan_ended_at']<=max_age_ms)
        if not valid:raise ValueError('Ground threat lens is incomplete, stale or belongs to another scope')
        threats=[]
        for entity in reply['scan_entities']:
            if type(entity.get('alive'))is not bool or type(entity.get('hostile'))is not bool:raise ValueError('Entity schema is not a native scan-end observation')
            if not(entity['alive']and entity['hostile']):continue
            pos=entity['pos']
            if not isinstance(pos,list)or len(pos)!=3 or any(type(n)not in(int,float)or not math.isfinite(n)for n in pos):raise ValueError('Incomplete hostile position')
            if math.hypot(pos[0]-foot[0],pos[2]-foot[2])<=25:threats.append(entity)
        return {'safe_now':not threats,'threats':threats,'sampled_at':reply['scan_ended_at'],'required_bounds':{'min':low,'max':high},'scope':ENTITY_SCOPE,'future_safety_not_proven':True}
    except(KeyError,TypeError,OverflowError)as error:raise ValueError('Unproved ground threat observation')from error
