"""Persistent routing from Kit's actual storage records; never inventory credit."""
from collections import Counter
import copy
import json
from pathlib import Path
import time

from kit_runtime.journal import write_json


def server_key(value):return value.strip().lower().removesuffix(':25565') if isinstance(value,str) else ''


def _read(path):
    path=Path(path)
    for attempt in range(3):
        try:
            if not path.exists():return None
            if path.stat().st_size>8_000_000:raise ValueError('Oversized storage record')
            value=json.loads(path.read_text())
            if not isinstance(value,dict):raise ValueError('Invalid storage object')
            return value
        except (OSError,ValueError):
            if attempt==2:return None
            time.sleep(.03) # Native config saving may briefly be in progress.


def _scope(state):
    server=server_key(state.get('server'));dimension=state.get('dimension')
    if not server or not isinstance(dimension,str):return None
    world=state.get('world_id','') if server=='singleplayer' else ''
    if server=='singleplayer' and not world:world='session:'+str(state.get('world_session',''))
    return {'server':server,'dimension':dimension,'world_id':world}


def _pos(value):return isinstance(value,list) and len(value)==3 and all(type(n)is int for n in value)


def _counts(items):
    counts=Counter()
    if not isinstance(items,list):return None
    for r in items:
        item=r.get('item',r.get('id')) if isinstance(r,dict) else None
        count=r.get('count') if isinstance(r,dict) else None
        if not isinstance(item,str) or not item.startswith('minecraft:') or type(count)is not int or count<0:return None
        if count:counts[item]+=count
    return dict(counts)


def index_path(root):return Path(root).parent/'storage-route-index.json'


def records(client,state=None):
    """Merge saved Kit observations with exact post-transfer menu observations.

    ``counts`` includes known shulker contents; ordinary depot exchange can
    withdraw only ``loose_counts``. Packed stock must go through the existing
    take_packed_materials workflow, which reopens and verifies the real box.
    """
    root=getattr(client,'root',None);state=state or client.status();scope=_scope(state)
    if root is None or scope is None:return []
    config=_read(Path(root).parent.parent/'twob2tkit.json')or{}
    result=[]
    for r in config.get('storageSnapshots',[]):
        if not isinstance(r,dict):continue
        if (server_key(r.get('server'))!=scope['server'] or r.get('dimension')!=scope['dimension']
                or r.get('worldId','')!=scope['world_id'] or r.get('status')=='unknown_scope'):continue
        ender=r.get('blockId')=='minecraft:ender_chest'
        if ender and (not state.get('player_uuid')or r.get('playerId')!=state['player_uuid']):continue
        p=[r.get(k)for k in ('x','y','z')];counts=_counts(r.get('items'))
        if not _pos(p) or counts is None:continue
        aliases=r.get('containerPositions')or[p]
        if not isinstance(aliases,list)or not 1<=len(aliases)<=2 or any(not _pos(a)for a in aliases)or p not in aliases:continue
        missing=r.get('status')=='missing'
        if missing:counts={}
        result.append({'scope':scope,'pos':p,'aliases':aliases,'counts':counts,'loose_counts':counts,'missing':missing,
            'observed_at':r.get('lastSeenEpochMillis',0),'block_id':r.get('blockId'),
            'player_uuid':r.get('playerId',''),'dirty':bool(r.get('contentsDirty')),
            'origin':'kit_storageSnapshots','packed_unknown':any(k.endswith('shulker_box')for k in counts)})
    own=_read(index_path(root))or{}
    for r in own.get('records',[]):
        if not isinstance(r,dict)or r.get('scope')!=scope:continue
        if r.get('block_id')=='minecraft:ender_chest'and r.get('player_uuid')!=state.get('player_uuid'):continue
        p=r.get('pos')
        if not _pos(p)or not isinstance(r.get('counts'),dict):continue
        native=next((n for n in result if p in n['aliases']),None)
        if native and native.get('missing'):continue
        # Equal top-level totals retain nested slot detail. A newer real native
        # observation with different totals replaces the old routing hint.
        if native and native['observed_at']>r.get('observed_at',0) and native['loose_counts']!=r.get('loose_counts'):continue
        if native:
            r={**r,'aliases':native['aliases'],'dirty':native['dirty']or r.get('dirty',False)}
            result.remove(native)
        result.append(r)
    return result


def select_destinations(client,positions,deposit):
    """Prefer recorded receiving space; counts remain routing hints only."""
    state=client.status();held=_counts(state.get('inventory',[]))or{}
    wanted={i:held.get(i,0)-n for i,n in deposit.items()if held.get(i,0)>n}
    saved=records(client,state);known=[];unknown=[];full=[]
    for pos in positions:
        record=next((r for r in saved if list(pos)in r.get('aliases',[r['pos']])),None)
        if record and record.get('missing'):full.append(list(pos));continue
        rows=record.get('slots')if record and not record.get('dirty')else None
        if not isinstance(rows,list)or len(rows)not in (27,54):unknown.append(list(pos));continue
        capacity={item:sum(64 if not r.get('count',0)else max(0,64-r['count'])
                         if r.get('item')==item else 0 for r in rows)for item in wanted}
        if any(capacity.values()):known.append((sum(min(wanted[i],capacity[i])for i in wanted),list(pos)))
        else:full.append(list(pos))
    known.sort(key=lambda r:-r[0])
    return {'positions':[p for _,p in known]+unknown,'skipped_known_full':full,
            'source':'persistent_local_storage','inventory_credit':0}


def select_sources(client,positions,targets,*,ender=False,reserve_empty=None,loose_only=False):
    """Known useful sources first; known irrelevant sources are never reopened."""
    if type(loose_only)is not bool:raise ValueError('Loose storage routing must be explicit boolean')
    state=client.status();saved=records(client,state);wanted=set(targets);ranked=[];unknown=[];skipped=[];packed=[]
    bag=[r for r in state.get('inventory',[])if r.get('slot',99)<36]
    capacity_blocked=[]
    if reserve_empty is not None and len(bag)==36 and {r.get('slot')for r in bag}==set(range(36)):
        empty=sum(not r.get('count',0)for r in bag)-reserve_empty
        held=Counter()
        for r in bag:held[r.get('item')]+=r.get('count',0)
        wanted={i for i,n in targets.items()if held[i]<n}
        capacity_blocked=[i for i in wanted if empty<=0 and not any(
            r.get('item')==i and 0<r.get('count',0)<r.get('max_stack',r.get('count',0))for r in bag)]
        wanted-=set(capacity_blocked)
    if not wanted:
        return {'positions':[],'skipped_known_empty':[],'capacity_blocked_items':capacity_blocked,
                'source':'persistent_local_storage','inventory_credit':0}
    for number,pos in enumerate(positions):
        pos=list(pos)
        candidates=[r for r in saved if (r.get('block_id')=='minecraft:ender_chest')==ender
                    and (ender or pos in r.get('aliases',[r['pos']]))]
        record=max(candidates,key=lambda r:r.get('observed_at',0),default=None)
        if record is None:unknown.append((number,pos));continue
        quantities=record.get('loose_counts',record['counts'])if loose_only else record['counts']
        available=sum(quantities.get(i,0)for i in wanted)
        if loose_only:
            inside={i:record['counts'].get(i,0)-quantities.get(i,0)for i in wanted
                    if record['counts'].get(i,0)>quantities.get(i,0)}
            if inside:packed.append({'pos':pos,'items':inside,'requires_packed_access':True})
        if available:ranked.append((-available,number,pos))
        elif record.get('packed_unknown'):unknown.append((number,pos))
        else:skipped.append(pos)
    return {'positions':[r[2]for r in sorted(ranked)]+[p for _,p in unknown],
            'skipped_known_empty':skipped,'capacity_blocked_items':capacity_blocked,
            'packed_candidates':packed,'loose_only':loose_only,
            'source':'persistent_local_storage','inventory_credit':0}


def bind_source(client,state,pos,block_id):
    if getattr(client,'root',None)is None:return
    client.storage_source={'pos':list(pos),'block_id':block_id,'menu_id':state['menu']['id'],
                           'world_session':state.get('world_session')}
    remember_current(client,state)


def remember_current(client,state=None):
    """Persist the complete actual menu after open and every confirmed transfer."""
    source=getattr(client,'storage_source',None);root=getattr(client,'root',None)
    if source is None or root is None:return False
    state=state or client.status();scope=_scope(state);menu=state.get('menu')or{}
    rows=menu.get('slots')or[]
    if (scope is None or state.get('world_session')!=source['world_session']
            or menu.get('id')!=source['menu_id']or menu.get('type')not in ('ChestMenu','ShulkerBoxMenu')
            or menu.get('cursor',{}).get('count')!=0 or len(rows)not in (63,90)
            or {r.get('slot')for r in rows}!=set(range(len(rows)))):return False
    loose=_counts(rows[:-36])
    if loose is None:return False
    counts=Counter(loose);packed_unknown=False
    for r in rows[:-36]:
        if r.get('count')==1 and r.get('item','').endswith('shulker_box'):
            packed_unknown|='contains'not in r
            children=_counts(r.get('contains',[]))
            if children is not None:counts.update(children)
    p=source['pos'];path=index_path(root);book=_read(path)
    if book is None and path.exists():raise RuntimeError('Local storage index unreadable; preserve original record')
    book=book or{'schema':1,'records':[]}
    previous=[r for r in book.get('records',[])if r.get('scope')==scope and r.get('pos')==p
              and r.get('player_uuid','')==(state.get('player_uuid','')if source['block_id']=='minecraft:ender_chest'else'')]
    book['records']=[r for r in book.get('records',[])if r not in previous]
    book['records'].append({'scope':scope,'pos':p,'aliases':[p],'block_id':source['block_id'],
        'player_uuid':state.get('player_uuid','')if source['block_id']=='minecraft:ender_chest'else'',
        'observed_at':state['time'],'world_session':state.get('world_session'),'menu_id':menu['id'],
        'counts':dict(counts),'loose_counts':loose,'slots':copy.deepcopy(rows[:-36]),
        'origin':'actual_open_menu_after_confirmed_transfer','dirty':False,'packed_unknown':packed_unknown,
        'inventory_credit':0})
    book['records']=sorted(book['records'],key=lambda r:r.get('observed_at',0))[-512:]
    path.parent.mkdir(parents=True,exist_ok=True);write_json(path,book);return True
