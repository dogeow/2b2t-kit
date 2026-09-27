"""Temporary two-cell concrete work enclosure with a recoverable ceiling hatch."""
import json,time,math
from pathlib import Path
from build_supervisor import stocks
from projection_wood import use_with_margin
from work_access import ApproachUnavailable

AIR='Block{minecraft:air}'
HATCH_ITEMS=('minecraft:cobblestone','minecraft:cobbled_deepslate','minecraft:dirt')
FACES=[((0,-1,0),'up'),((-1,0,0),'east'),((1,0,0),'west'),((0,0,-1),'south'),((0,0,1),'north'),((0,1,0),'down')]


def plan(stand):
    x,y,z=stand
    work=[x+1,y-1,z];leaf=[x+2,y-1,z];hatch=[x,y+3,z]
    rim=[(xx,zz) for xx in range(x-1,x+3) for zz in range(z-1,z+2)
         if xx in (x-1,x+2) or zz in (z-1,z+1)]
    walls=[[xx,yy,zz] for yy in range(y-1,y+3) for xx,zz in rim if [xx,yy,zz]!=leaf]
    roof=[[xx,y+3,zz] for xx in range(x-1,x+3) for zz in range(z-1,z+2) if [xx,y+3,zz]!=hatch]
    roof.sort(key=lambda p:p==[x+1,y+3,z])
    return {'stand':list(stand),'cell':work,'leaf':leaf,'hatch':hatch,'blocks':walls+roof,
            'min':[x-2,y-3,z-2],'max':[x+3,y+5,z+2]}


def scan(client,low,high):
    reply=client.request('scan',min=low,max=high,details=True)
    if 'blocks' not in reply:raise RuntimeError('Shelter survey unavailable')
    return {tuple(v['pos']):v for v in reply['blocks']}


def dry_anchors(rows,pos,replaceable_plant=False):
    current=rows.get(tuple(pos),{})
    candidates=[(list(pos),'up',current['state'])] if replaceable_plant else []
    for delta,face in FACES:
        p=tuple(a+b for a,b in zip(pos,delta));anchor=rows.get(p)
        if anchor and anchor.get('solid') and not anchor.get('block_entity') and not anchor.get('fluid'):
            candidates.append((list(p),face,anchor['state']))
    return candidates


def land_on_top(client,block):
    row=scan(client,block,block).get(tuple(block),{})
    if not row.get('solid') or row.get('fluid'):raise RuntimeError('A dry verified landing block is required')
    x,y,z=block
    result=client.request('approach_block',pos=block,face='up',expected_state=row['state'],stand_distance=.65,seconds=90)
    if result.get('phase')!='done':
        current=client.status()['pos']
        if result.get('detail')!='Depot route has no verified movement' or abs(current[1]-y-1)>1 or math.hypot(current[0]-x-.5,current[2]-z-.5)>1.5:
            raise RuntimeError('Precise landing approach failed: '+str(result.get('detail')))
    client.checked('walk',target=[x+.5,y+1,z+.5],arrival=.15,restore_flight=False,seconds=20)
    deadline=time.monotonic()+4
    while True:
        s=client.request('snapshot')
        if s.get('on_ground') and abs(s['pos'][1]-y-1)<.2 and math.hypot(s['pos'][0]-x-.5,s['pos'][2]-z-.5)<.3 and math.hypot(s['velocity'][0],s['velocity'][2])<.03:return
        if time.monotonic()>deadline:raise RuntimeError('Landing did not settle; no placement was attempted')
        time.sleep(.15)


def place(client,pos,item,ledger,leaf=False,interior_roof=False):
    x,y,z=pos;rows=scan(client,[x-1,y-1,z-1],[x+1,y+1,z+1]);old=rows.get(tuple(pos),{})
    if old.get('state','').startswith('Block{'+item+'}'):
        if leaf and 'waterlogged=true' not in old['state']:raise RuntimeError('Existing leaf is not waterlogged')
        return
    grass=old.get('replaceable') and old.get('state') in ('Block{minecraft:short_grass}','Block{minecraft:fern}')
    if old and not old['state'].startswith('Block{minecraft:water}') and not grass:
        if old.get('solid') and not old.get('block_entity') and not leaf:return
        raise RuntimeError('Preserve occupied shelter target: '+str(pos))
    if leaf and old.get('state')!='Block{minecraft:water}[level=0]':
        raise RuntimeError('Only an observed source-water cell may become the waterlogged leaf')
    candidates=dry_anchors(rows,pos,grass)
    if not candidates:raise RuntimeError('No actual supporting face for shelter block '+str(pos))
    if client.status()['health']<19:raise RuntimeError('Stop shelter work and recover health')
    roof=pos[1]==ledger['layout']['hatch'][1]
    if interior_roof:
        stand=ledger['layout']['stand'];land_on_top(client,[stand[0],stand[1]-1,stand[2]])
    elif roof:
        platforms=[r for p,r in rows.items() if p[1] in (y,y-1) and abs(p[0]-x)+abs(p[2]-z)==1 and r.get('solid') and not r.get('fluid') and not r.get('block_entity')]
        if not platforms:raise RuntimeError('Roof has no adjacent dry landing platform')
        platform=max(platforms,key=lambda r:r['pos'][1])
        land_on_top(client,platform['pos'])
    client.checked('select_item',item=item)
    before=stocks(client.status()).get(item,0)
    if not before:raise RuntimeError('Shelter material exhausted')
    placed=False
    for anchor,face,state in candidates:
        fresh=scan(client,pos,pos).get(tuple(pos),{}).get('state',AIR)
        if fresh!=old.get('state',AIR):raise RuntimeError('Shelter target changed before placement')
        def before_use():
            current=scan(client,pos,pos).get(tuple(pos),{}).get('state',AIR)
            if current!=old.get('state',AIR):raise RuntimeError('Shelter target changed while approaching')
            p=client.status()['pos']
            if p[0]+.3>x and p[0]-.3<x+1 and p[2]+.3>z and p[2]-.3<z+1 and p[1]+1.8>y and p[1]<y+1:
                raise ApproachUnavailable('Do not place the enclosure block through the player')
        stable_access=False
        for attempt in range(2):
            # Covered grass naturally turns to dirt. Refresh a still-solid,
            # non-container support before movement; no placement is replayed.
            current_anchor=scan(client,anchor,anchor).get(tuple(anchor),{})
            if not current_anchor or current_anchor.get('block_entity') or current_anchor.get('fluid') or not (current_anchor.get('solid') or grass and anchor==pos):break
            try:
                if roof:
                    before_use()
                    result=client.request('interact',pos=anchor,face=face,expected_state=current_anchor['state'],expected_hand=item)
                    if result.get('phase')=='error' and result.get('detail') in ('Target interaction face is occluded or out of reach','Interaction became occluded while rotating'):break
                    if result.get('phase')!='done':raise RuntimeError('Interior ceiling placement not confirmed')
                else:use_with_margin(client,anchor,current_anchor['state'],item,(face,),before_use)
                stable_access=True;break
            except ApproachUnavailable:break
            except RuntimeError as error:
                if str(error) not in ('Work block state changed','Work target changed during access recovery') or attempt:raise
        if not stable_access:continue
        placed=True;break
    if not placed:
        (client.out/'unplaced-shelter-block.json').write_text(json.dumps({'pos':pos,'anchors':candidates,'player':client.status()['pos']},ensure_ascii=False,indent=2))
        raise RuntimeError('No visible shelter placement face at '+str(pos))
    deadline=time.monotonic()+6
    while True:
        observed=scan(client,pos,pos).get(tuple(pos),{}).get('state',AIR)
        used=before-stocks(client.status()).get(item,0)
        if observed.startswith('Block{'+item+'}') and used==1:
            if leaf and 'waterlogged=true' not in observed:raise RuntimeError('Placed leaf did not retain water')
            entry={'pos':list(pos),'before':old.get('state',AIR),'after':observed,'item':item,'owned':True}
            ledger['placed'].append(entry);Path(ledger['path']).write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
            return
        if time.monotonic()>deadline:raise RuntimeError('Placement not confirmed; never replay the use blindly')
        time.sleep(.2)


def build(client,stand,path):
    layout=plan(stand);path=Path(path).resolve()
    ledger=json.loads(path.read_text()) if path.exists() else {'path':str(path),'layout':layout,'placed':[],'complete':False}
    ledger['path']=str(path)
    if ledger['layout']!=layout:
        old=ledger['layout']
        if ({k:v for k,v in old.items() if k!='blocks'}!={k:v for k,v in layout.items() if k!='blocks'} or set(map(tuple,old['blocks']))!=set(map(tuple,layout['blocks']))):
            raise RuntimeError('Temporary shelter geometry changed')
        ledger['layout']=layout;path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
    before=scan(client,layout['min'],layout['max'])
    for x in (stand[0],stand[0]+1):
        for y in range(stand[1],stand[1]+3):
            if (x,y,stand[2]) in before:raise RuntimeError('Keep the two work cells clear of existing blocks')
    if tuple(layout['hatch']) in before:raise RuntimeError('Keep an open exit shaft before enclosure construction')
    if not path.exists():
        ledger['baseline']=list(before.values());path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
    place(client,layout['leaf'],'minecraft:oak_leaves',ledger,leaf=True)
    for pos in layout['blocks']:
        previous=len(ledger['placed'])
        place(client,pos,'minecraft:cobblestone',ledger,interior_roof=pos==[stand[0]+1,stand[1]+3,stand[2]])
        if len(ledger['placed'])>previous:print('SHELTER',len(ledger['placed']),flush=True)
    final=scan(client,layout['min'],layout['max'])
    if any(not final.get(tuple(p),{}).get('solid') for p in layout['blocks']):raise RuntimeError('Shelter shell is incomplete')
    ledger['complete']=True;path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2));return ledger


def save_ledger(ledger):
    Path(ledger['path']).write_text(json.dumps(ledger,ensure_ascii=False,indent=2))


def choose_hatch_item(state):
    carried=stocks(state)
    return next((item for item in HATCH_ITEMS if carried.get(item,0)>0),None)


def exit_station(client,ledger):
    from material_cleanup import complete
    stand=ledger['layout']['stand'];hatch=ledger['layout']['hatch']
    row=scan(client,hatch,hatch).get(tuple(hatch))
    if row:
        hatch_item=ledger.get('hatch_item','minecraft:cobblestone')
        if (hatch_item not in HATCH_ITEMS or not ledger.get('hatch_owned')
                or row['state']!='Block{'+hatch_item+'}'):
            raise RuntimeError('Do not remove an unowned or changed ceiling hatch')
        client.checked('select_item',item='minecraft:diamond_pickaxe')
        face='down' if client.status()['pos'][1]<hatch[1] else 'up'
        client.checked('mine_block',pos=hatch,face=face,expected_state=row['state'],seconds=12)
        if scan(client,hatch,hatch).get(tuple(hatch)):raise RuntimeError('Ceiling opening not confirmed')
    ledger['hatch_owned']=False;save_ledger(ledger)
    current=client.status()['pos']
    if current[1]<hatch[1]+1 and (abs(current[1]-stand[1])>.2 or math.hypot(current[0]-stand[0]-.5,current[2]-stand[2]-.5)>.3):
        land_on_top(client,[stand[0],stand[1]-1,stand[2]])
    if client.status()['pos'][1]<hatch[1]+1.2:
        client.checked('navigate',target=[stand[0]+.5,stand[1]+5,stand[2]+.5],arrival=1,seconds=20)
    if client.status()['pos'][1]<hatch[1]+1:raise RuntimeError('Player has not exited the ceiling opening')
    complete(client,ledger['path']+'#hatch')


def light_station(client,ledger):
    x,y,z=ledger['layout']['stand'];target=[x+1,y+1,z];anchor=[x+2,y+1,z]
    existing=scan(client,target,target).get(tuple(target),{}).get('state',AIR)
    if existing.startswith('Block{minecraft:wall_torch}'):return
    if existing!=AIR:raise RuntimeError('Preserve occupied interior light position')
    state=client.status();menu=state['menu'];offhand=menu['slots'][45]
    if menu['type']!='InventoryMenu' or offhand['item']!='minecraft:torch' or not offhand['count']:
        raise RuntimeError('An offhand torch is required before closing the work enclosure')
    original=menu['slots'][41].copy()  # hotbar slot 5
    client.checked('slot_click',menu_id=menu['id'],slot=45,expected_item=offhand['item'],expected_count=offhand['count'],kind='swap',button=5)
    try:
        client.checked('select_item',item='minecraft:torch',slot=5)
        block=scan(client,anchor,anchor)[tuple(anchor)]
        client.checked('interact',pos=anchor,face='west',expected_state=block['state'],expected_hand='minecraft:torch')
        if not scan(client,target,target).get(tuple(target),{}).get('state','').startswith('Block{minecraft:wall_torch}'):
            raise RuntimeError('Interior light placement not confirmed')
        ledger['light']={'pos':target,'owned':True};save_ledger(ledger)
    finally:
        current=client.status()['menu'];stored=current['slots'][45]
        if stored['item']==original['item'] and stored['count']==original['count']:
            client.checked('slot_click',menu_id=current['id'],slot=45,expected_item=stored['item'],expected_count=stored['count'],kind='swap',button=5)


def inside_hostiles(state,stand):
    known={'minecraft:zombie','minecraft:creeper','minecraft:skeleton','minecraft:spider','minecraft:drowned','minecraft:husk','minecraft:witch'}
    x,y,z=stand
    return [e for e in state.get('entities',[]) if (e.get('hostile') or e.get('type') in known)
            and len(e.get('pos',[]))==3 and x-.5<e['pos'][0]<x+2.5
            and y-1<e['pos'][1]<y+3 and z-.75<e['pos'][2]<z+1.75]


def enter_station(client,path):
    from material_cleanup import register
    path=Path(path).resolve();ledger=json.loads(path.read_text());ledger['path']=str(path);layout=ledger['layout'];stand=layout['stand'];hatch=layout['hatch']
    if not ledger.get('complete'):raise RuntimeError('Enclosure must be verified before entering')
    if choose_hatch_item(client.status()) is None:
        raise RuntimeError('A carried cobblestone, cobbled deepslate or dirt block is required before entering')
    shell=scan(client,layout['min'],layout['max'])
    if any(not shell.get(tuple(p),{}).get('solid') for p in layout['blocks']):raise RuntimeError('Enclosure wall or roof changed')
    leaf=shell.get(tuple(layout['leaf']),{})
    if 'waterlogged=true' not in leaf.get('state',''):raise RuntimeError('Enclosed water source changed')
    if tuple(hatch) in shell:exit_station(client,ledger)
    land_on_top(client,[stand[0],hatch[1],stand[2]-1])
    if inside_hostiles(client.request('snapshot'),stand):raise RuntimeError('Hostile inside work enclosure; do not descend')
    land_on_top(client,[stand[0],stand[1]-1,stand[2]])
    state=client.status()
    if abs(state['pos'][1]-stand[1])>.2 or math.hypot(state['pos'][0]-stand[0]-.5,state['pos'][2]-stand[2]-.5)>.3:
        raise RuntimeError('Player is not on the verified dry interior floor')
    light_station(client,ledger)
    register(client,ledger['path']+'#hatch',lambda:exit_station(client,ledger))
    anchor=[stand[0]+1,hatch[1],stand[2]];row=scan(client,anchor,anchor)[tuple(anchor)]
    if scan(client,hatch,hatch):raise RuntimeError('Hatch changed before closing')
    hatch_item=choose_hatch_item(client.status())
    if hatch_item is None:raise RuntimeError('Carried hatch material changed before closure')
    client.checked('select_item',item=hatch_item);before=stocks(client.status()).get(hatch_item,0)
    ledger['hatch_item']=hatch_item;ledger['hatch_owned']=False;save_ledger(ledger)
    client.checked('interact',pos=anchor,face='west',expected_state=row['state'],expected_hand=hatch_item)
    deadline=time.monotonic()+5
    while True:
        current=scan(client,hatch,hatch).get(tuple(hatch),{})
        if current.get('state')=='Block{'+hatch_item+'}' and stocks(client.status()).get(hatch_item,0)==before-1:break
        if time.monotonic()>deadline:raise RuntimeError('Ceiling closure not confirmed')
        time.sleep(.2)
    ledger['hatch_owned']=True;save_ledger(ledger);return ledger
