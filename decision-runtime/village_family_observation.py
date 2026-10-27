"""Read-only identity and bed binding checks for a guarded family transfer."""
import math
from projection_completion import block_state

DELTAS={'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}

def sleeping_family_homes(state,frame,rows,parents,children):
    if len(parents)!=2 or len(children)!=2 or len(set(parents)|set(children))!=4:
        raise ValueError('Two distinct founders and two distinct offspring required')
    if not frame or frame.get('world_session')!=state.get('world_session'):return None
    people={v['uuid']:v for v in state.get('loaded_villagers',{}).get('villagers',[])}
    flags={v['uuid']:v for v in frame.get('villagers',[])};homes={}
    for uid in list(parents)+list(children):
        if uid not in people or uid not in flags:return None
        actor=people[uid];flag=flags[uid]
        if(actor.get('health')!=20 or flag.get('client_health')!=20 or actor.get('is_baby')is not False
                or flag.get('is_baby')is not False or flag.get('passenger')is not False
                or flag.get('no_ai_client_flag')is not False or flag.get('sleeping')is not True):return None
        p=actor.get('pos')
        if not isinstance(p,list)or len(p)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in p):return None
        cell=tuple(math.floor(v)for v in p)
        try:
            name,properties=block_state(rows[cell]['state']);direction=properties['facing'];delta=DELTAS[direction]
            if name!='minecraft:white_bed'or properties['part']not in('head','foot'):return None
            foot=tuple(cell[i]-delta[i]for i in range(3))if properties['part']=='head'else cell
            head=tuple(foot[i]+delta[i]for i in range(3))
            for position,part in [(foot,'foot'),(head,'head')]:
                block,prop=block_state(rows[position]['state'])
                if block!='minecraft:white_bed'or prop.get('part')!=part or prop.get('facing')!=direction:return None
        except(KeyError,ValueError):return None
        if any(set((foot,head))&set((tuple(v['foot']),tuple(v['head'])))for v in homes.values()):return None
        homes[uid]={'foot':list(foot),'head':list(head),'facing':direction}
    return {'parents':{uid:homes[uid]for uid in parents},'children':{uid:homes[uid]for uid in children}}

def founders_still_asleep(state,frame,parents):
    if not frame or frame.get('world_session')!=state.get('world_session'):return False
    flags={v['uuid']:v for v in frame.get('villagers',[])}
    return all(uid in flags and flags[uid].get('sleeping')is True
               and flags[uid].get('client_health')==20 and flags[uid].get('passenger')is False
               and flags[uid].get('no_ai_client_flag')is False for uid in parents)
