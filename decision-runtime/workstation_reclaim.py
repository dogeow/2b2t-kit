"""Read-only admission after actual job release; never a substitute for native reset/placement guards."""
import math

def replacement_ready(state,frame,release,inside,outside,work):
    try:
        sequence=release['native_sequence']
        if(type(sequence)is not int or sequence<=0 or release['server_ack_sequence']!=sequence
           or release['uuid']!=outside or release['world_session']!=state['world_session']
           or type(release['time'])is not int or not release['time']<=state['time']
           or frame['world_session']!=state['world_session']or not 0<=state['time']-frame['time']<=1000
           or state['connected']is not True or state['health']!=20 or state['manual_movement']is not False):return False
        actors={v['uuid']:v for v in state['loaded_villagers']['villagers']};flags={v['uuid']:v for v in frame['villagers']}
        target=actors[inside];other=actors[outside];target_flag=flags[inside];other_flag=flags[outside]
        for actor,flag in ((target,target_flag),(other,other_flag)):
            if(actor['health']!=20 or actor['is_baby']is not False or flag['passenger']is not False
               or flag['client_health']!=20 or flag['is_baby']is not False
               or actor['villager']['profession']!='minecraft:none'
               or not isinstance(actor['pos'],list)or len(actor['pos'])!=3
               or any(type(v)not in(int,float)or not math.isfinite(v)for v in actor['pos'])):return False
        point=[work[0]+.5,float(work[1]),work[2]+.5]
        return(target_flag['sleeping']is False and math.dist(target['pos'],point)<=1.65
               and math.dist(other['pos'],point)>=6)
    except(KeyError,TypeError,ValueError):return False
