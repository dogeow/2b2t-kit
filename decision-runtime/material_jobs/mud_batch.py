"""Read-only capacity offer for the real16-cell mud worker, not a whole-recipe plan."""
import math


def carried_visit_target(request,profile,state,item,final_count):
    if(request.get('mode')!='projection'or item!='minecraft:mud_bricks'
            or profile.get('mud_station',{}).get('authorized')is not True
            or profile.get('mud_bucket_source',{}).get('authorized')is not True
            or state.get('bottle_water_protocol',0)<1
            or state.get('world_session')!=request.get('context',{}).get('world_session')):return None
    rows=[r for r in state.get('inventory',[])if 0<=r.get('slot',-1)<36]
    if(len(rows)!=36 or {r['slot']for r in rows}!=set(range(36))
            or any(type(r.get('count'))is not int or r['count']<0 for r in rows)):return None
    bottle=sum(r['count']for r in rows if r.get('item')=='minecraft:glass_bottle')
    plain=[r for r in rows if r.get('item')==item and r['count']>0
           and set(r)=={'slot','item','count','max_stack'}and r.get('max_stack')==64]
    if bottle!=1 or not plain or sum(not r['count']for r in rows)<3:return None
    held=sum(r['count']for r in rows if r.get('item')==item)
    if type(final_count)is not int or final_count<=held:return None
    gain=min(16,final_count-held);rounded=math.ceil(gain/4)*4
    if sum(64-r['count']for r in plain)<rounded:return None
    return held+gain
