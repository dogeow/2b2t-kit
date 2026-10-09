"""Journaled temporary dirt caps for axis-y wood on a dry floating map plate.

Every cap starts as observed AIR. Only confirmed owned dirt is recovered. All
wood placement and stripping remain normal Kit projection_wood operations.
"""
import json,math,time
from collections import deque
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_wood import finish_beams,_scoped_audit,use_with_margin
from work_access import approach_faces
from material_cleanup import register,complete
from owned_air_escape import wait_known_idle

DIRT='Block{minecraft:dirt}'
RAW='minecraft:cherry_wood'
EXPECTED='Block{minecraft:stripped_cherry_wood}[axis=y]'
FACE={(1,0):'east',(-1,0):'west',(0,1):'south',(0,-1):'north'}


def plan_caps(target,observed,matched,low,high,max_caps=4):
    """A short AIR cap bridge rooted above an actual matched noninteractive cube."""
    if type(max_caps)is not int or not 2<=max_caps<=8:
        raise ValueError('A cap bridge is bounded to2..8 actual AIR cells')
    pos=tuple(target);by={tuple(r['pos']):r for r in observed}
    def air(p):return p not in by
    def valid(p):
        row=by.get(p)
        return (low[0]<=p[0]<=high[0]and low[2]<=p[2]<=high[2]
                and air((p[0],p[1]+1,p[2]))
                and (row is None or row.get('fluid')is False and row.get('block_entity')is False))
    if not air(pos)or not valid(pos):return None
    queue=deque([(pos,[pos])]);seen={pos}
    while queue:
        node,path=queue.popleft()
        row=by.get(node)
        if (node in matched and row and row.get('solid')is True
                and row.get('fluid')is False and row.get('block_entity')is False):
            bottom_path=list(reversed(path));caps=[[p[0],p[1]+1,p[2]]for p in bottom_path]
            return {'target':list(pos),'base':list(node),'base_state':row['state'],'caps':caps}
        if len(path)>=max_caps:continue
        for dx,dz in FACE:
            q=(node[0]+dx,node[1],node[2]+dz)
            if q not in seen and valid(q):seen.add(q);queue.append((q,path+[q]))
    return None


def run_one(c,target,out,checkpoint,*,max_caps=4):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    before=checkpoint();key=before['projection_selection']['key'];world=c.world
    low=before['projection_selection']['min'];high=before['projection_selection']['max']
    book={'schema':1,'world_session':world,'task_session':c.task,'placement_key':key,
          'target':list(target),'pending':None,'owned_caps':[],'complete':False}
    def save():write_json(out/'progress.json',book)
    save()
    def state():
        s=checkpoint()
        if (s['world_session']!=world or s['projection_selection']['key']!=key
                or s['health']!=20 or s['food']<18 or s['manual_movement']or s['screen']
                or not s['guard_armed']or not s['guard_pve_only']):
            raise RuntimeError('Cap construction scope or survival changed')
        return s
    def scan(lo,hi):
        state();r=c.checked('scan',min=lo,max=hi,details=True,seconds=30);wait_known_idle(c)
        if (r['scan_cells_read']!=r['scan_total_cells'] or r['scan_total_cells']!=math.prod(hi[i]-lo[i]+1 for i in range(3))
                or r['scan_start_revision']!=r['scan_end_revision']or r['world_session']!=world):
            raise RuntimeError('Incomplete current cap volume')
        return r
    def at(pos):
        r=scan(pos,pos);return next((v['state']for v in r['blocks']if v['pos']==pos),'AIR')
    def settled(pos,expected,item,total):
        frames=[];deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            actual=at(pos);s=state()
            if actual==expected and inventory_counts(s).get(item,0)==total:
                if not frames or s['time']>frames[-1]['time']:frames.append(s)
                if len(frames)>=2 and frames[-1]['time']-frames[0]['time']>=400:return frames
            else:frames=[]
            time.sleep(.1)
        raise RuntimeError('Cap state/stock conservation unproved; preserve original action')
    audit=c.request('projection_audit')['projection_audit'];_scoped_audit(state(),audit,key,world,before['server'],before['dimension'])
    row=next((r for r in audit['mismatches']if r['pos']==list(target)),None)
    if not row or row['expected']!=EXPECTED or row['actual']!='Block{minecraft:air}'or row['fluid']or row['adjacent_fluid']or not row['neighbors_loaded']:
        raise RuntimeError('Exact missing dry axis-y cherry wood required')
    mismatch={tuple(r['pos'])for r in audit['mismatches']}
    lo=[max(low[0],target[0]-max_caps),target[1],max(low[2],target[2]-max_caps)]
    hi=[min(high[0],target[0]+max_caps),target[1]+2,min(high[2],target[2]+max_caps)]
    volume=scan(lo,hi);write_json(out/'current-cap-volume.json',volume)
    matched={tuple(r['pos'])for r in volume['blocks']if r['pos'][1]==target[1]and tuple(r['pos'])not in mismatch}
    plan=plan_caps(target,volume['blocks'],matched,low,high,max_caps)
    if not plan:raise RuntimeError('No bounded cap bridge above actual matched blocks')
    wood_before=inventory_counts(state()).get(RAW,0);dirt_before=inventory_counts(state()).get('minecraft:dirt',0)
    if wood_before<1 or dirt_before<len(plan['caps'])+1:raise RuntimeError('Actual raw wood/dirt capacity unavailable')
    book.update(plan=plan,wood_before=wood_before,dirt_before=dirt_before);save()
    cleanup_key='wood-caps:'+str(out.resolve())
    def cleanup():
        if book['pending']:raise RuntimeError('Unknown cap action retained; cleanup must not replay')
        for pos in reversed(book['owned_caps'][:]):
            if at(pos)!=DIRT:raise RuntimeError('Owned cap changed; no other block is removed')
            tool=next((r for r in state()['inventory']if r['item']in ('minecraft:diamond_shovel','minecraft:netherite_shovel')and r['count']==1 and r.get('durability',0)>=2),None)
            if tool is None:raise RuntimeError('Actual durable shovel required')
            face=approach_faces(c,pos,DIRT,('up','north','south','east','west'),seconds=30,stand_distance=2.4)
            c.checked('select_item',item=tool['item'],slot=tool['slot']);old=state();held=inventory_counts(old).get('minecraft:dirt',0)
            old_ids={e.get('uuid')for e in old.get('entities',[])if e.get('type')=='minecraft:item'}
            book['pending']={'op':'mine_owned_cap','pos':pos,'dirt_before':held};save()
            r=c.request('mine_block',pos=pos,face=face,expected_state=DIRT,seconds=30)
            if r.get('phase')!='done':raise RuntimeError('Cap mining not confirmed; no second mine')
            deadline=time.monotonic()+4
            while inventory_counts(state()).get('minecraft:dirt',0)!=held+1:
                s=state();drop=next((e for e in s.get('entities',[])if e.get('type')=='minecraft:item'and e.get('uuid')not in old_ids and e.get('stack',{}).get('item')=='minecraft:dirt'and e['stack'].get('count')==1 and math.dist(e['pos'],[v+.5 for v in pos])<=3),None)
                if drop:
                    book['pending']={'op':'pickup_owned_cap','uuid':drop['uuid'],'pos':pos,'dirt_before':held};save()
                    r=c.request('collect_item',expected_uuid=drop['uuid'],expected_item='minecraft:dirt',expected_count=1,seconds=30)
                    if r.get('phase')!='done':
                        if (r.get('phase')=='error' and r.get('detail')=='Drop is no longer loaded; observe again'
                                and inventory_counts(state()).get('minecraft:dirt',0)==held+1):
                            # Native pickup admission saw an already collected
                            # drop. Verify the cell/balance below; never resend.
                            pass
                        else:raise RuntimeError('Cap pickup not confirmed; no replay')
                    break
                if time.monotonic()>=deadline:raise RuntimeError('Owned cap drop missing; retain journal')
                time.sleep(.1)
            settled(pos,'AIR','minecraft:dirt',held+1)
            book['owned_caps'].remove(pos);book['pending']=None;save()
        if inventory_counts(state()).get('minecraft:dirt',0)!=dirt_before:raise RuntimeError('Dirt reserve not restored')
    register(c,cleanup_key,cleanup)
    for i,pos in enumerate(plan['caps']):
        anchor=plan['base']if i==0 else plan['caps'][i-1]
        expected=plan['base_state']if i==0 else DIRT
        face='up'if i==0 else FACE[(pos[0]-anchor[0],pos[2]-anchor[2])]
        if at(pos)!='AIR' or at(anchor)!=expected:raise RuntimeError('Cap AIR cell or anchor changed')
        approach_faces(c,anchor,expected,(face,),seconds=30,stand_distance=2.4)
        c.checked('select_item',item='minecraft:dirt');held=inventory_counts(state()).get('minecraft:dirt',0)
        if at(pos)!='AIR':raise RuntimeError('Cap target changed before placement')
        book['pending']={'op':'place_cap','pos':pos,'anchor':anchor,'face':face,'dirt_before':held};save()
        r=c.request('interact',pos=anchor,face=face,expected_state=expected,expected_hand='minecraft:dirt')
        if r.get('phase')!='done':raise RuntimeError('Cap placement uncertain; no repeat')
        frames=settled(pos,DIRT,'minecraft:dirt',held-1);write_json(out/('cap-'+str(i)+'-confirmed.json'),frames)
        book['owned_caps'].append(pos);book['pending']=None;save()
    book['pending']={'op':'axis_correct_place_and_strip','target':list(target),'wood_before':wood_before};save()
    result=finish_beams(c,limit=1,expected_key=key,expected_world=world,expected_server=before['server'],expected_dimension=before['dimension'],target_item='minecraft:stripped_cherry_wood',target_axis='y')
    write_json(out/'native-beam-result.json',result)
    if len(result['completed'])!=1 or result['completed'][0]['pos']!=list(target):raise RuntimeError('Exact owned-cap beam not completed')
    settled(list(target),EXPECTED,RAW,wood_before-1);book['pending']=None;save()
    cleanup();complete(c,cleanup_key)
    if at(list(target))!=EXPECTED:raise RuntimeError('Completed wood changed during cap cleanup')
    book.update(complete=True,actual_new_cells=1,dirt_restored=True,all_caps_removed=True);save();return book
