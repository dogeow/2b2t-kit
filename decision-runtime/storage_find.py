"""Read-only item lookup over Kit's storage records.

Answers "which recorded containers in this world hold item X". It never opens
containers or sends game requests; counts are routing hints, not stock proof.
"""
from pathlib import Path
import time

from material_storage_index import _read, _scope, records, server_key


def item_id(value):
    value=value.strip().lower()
    return value if ':' in value else 'minecraft:'+value


class _Records:
    """Minimal client shape that ``material_storage_index.records`` reads."""
    def __init__(self,root,state):self.root=root;self._state=state
    def status(self):return self._state


def _age_hours(observed_at,now):
    return round(max(0,now-observed_at/1000)/3600,1) if observed_at else None


def find(root,items,state,limit=20,now=None):
    now=time.time() if now is None else now
    wanted=[item_id(i) for i in items]
    here=state.get('pos')
    rows=records(_Records(root,state),state)
    result={}
    for item in wanted:
        hits=[]
        for r in rows:
            count=(r.get('counts')or{}).get(item,0);packed=(r.get('packed_counts')or{}).get(item,0)
            if not count and not packed or r.get('missing'):continue
            hit={'pos':r['pos'],'count':count,'block_id':r.get('block_id'),
                'confirmed':not r.get('dirty'),'observed_at':r.get('observed_at',0),
                'age_hours':_age_hours(r.get('observed_at',0),now)}
            if packed:hit['packed']=packed
            if isinstance(here,list)and len(here)==3:
                hit['distance']=round(sum((a-b)**2 for a,b in zip(r['pos'],here))**.5)
            hits.append(hit)
        # Confirmed records first, then the largest loose pile, then packed stock, nearest among equals.
        hits.sort(key=lambda h:(not h['confirmed'],-h['count'],-h.get('packed',0),h.get('distance',0)))
        result[item]={'total':sum(h['count']for h in hits),
            'confirmed_total':sum(h['count']for h in hits if h['confirmed']),
            'packed_total':sum(h.get('packed',0)for h in hits),
            'containers':len(hits),'top':hits[:limit]}
    return {'schema':1,'server':server_key(state.get('server')),'dimension':state.get('dimension'),
        'items':result,
        'unknown_shulker_containers':sum(1 for r in rows if r.get('packed_unknown')and not r.get('packed_known')and not r.get('missing')),
        'note':'仅为开箱缓存的路线提示，不证明当前有货；packed 是潜影盒内数量，不能直接取；取料用 materials start，以实际开箱为准'}


def match(root,text,state,limit=20):
    """Text search over recorded names, ids and enchantments (e.g. "mending"), loose and packed."""
    needle=text.strip().lower();scope=_scope(state)
    config=_read(Path(root).parent.parent/'twob2tkit.json')or{}
    hits=[]
    if needle and scope:
        for r in config.get('storageSnapshots',[]):
            if not isinstance(r,dict)or server_key(r.get('server'))!=scope['server']or r.get('dimension')!=scope['dimension']\
                    or r.get('worldId','')!=scope['world_id']or r.get('status')in('missing','unknown_scope'):continue
            if r.get('blockId')=='minecraft:ender_chest'and r.get('playerId')!=state.get('player_uuid'):continue
            found=[]
            for packed,key in ((False,'items'),(True,'packedItems')):
                for i in r.get(key)or[]:
                    if not isinstance(i,dict)or type(i.get('count'))is not int:continue
                    text_of=' '.join(str(i.get(k,''))for k in('id','name','searchTerms')).lower()
                    if needle in text_of:
                        found.append({'item':i.get('id'),'name':i.get('name'),'count':i['count'],'packed':packed,
                            **({'enchantments':i['searchTerms']}if i.get('searchTerms')else{})})
            if found:hits.append({'pos':[r.get('x'),r.get('y'),r.get('z')],'block_id':r.get('blockId'),
                'confirmed':not r.get('contentsDirty')and r.get('status')=='active','matches':found})
    hits.sort(key=lambda h:(not h['confirmed'],-sum(m['count']for m in h['matches']if not m['packed'])))
    return {'schema':1,'server':server_key(state.get('server')),'dimension':state.get('dimension'),'match':text,
        'containers':len(hits),'top':hits[:limit],
        'note':'仅为开箱缓存的路线提示，不证明当前有货；packed=true 在潜影盒内'}
