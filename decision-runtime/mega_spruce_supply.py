"""One journaled 2x2 spruce planting/growth through the retained Kit owner.

The caller supplies a currently inspected natural plot and a proven clear
planting pose. Every use is followed by inventory and world acknowledgement;
an unknown use is never retried. Harvest remains the native fixed-tree job.
"""
from pathlib import Path
from copy import deepcopy
import math,time
from material_plan import inventory_counts
from mega_spruce_growth import candidates,body_clear
from tree_planting_order import planting_order
from kit_runtime.journal import write_json


def natural_soil(row):
    name=row.get('state','').split('}',1)[0].removeprefix('Block{')
    return (row.get('solid')is True and not row.get('fluid')and not row.get('block_entity')
            and name in ('minecraft:grass_block','minecraft:dirt','minecraft:podzol'))


def roots(root):
    candidates(root)  # Validate the exact integer northwest root.
    return [[root[0]+x,root[1],root[2]+z] for x,z in ((0,0),(0,1),(1,0),(1,1))]


def growth_kind(rows,root):
    states=[rows.get(tuple(p),{}).get('state','') for p in roots(root)]
    if all(v.startswith('Block{minecraft:spruce_log}') for v in states):return 'grown'
    if all(v in ('Block{minecraft:spruce_sapling}[stage=0]','Block{minecraft:spruce_sapling}[stage=1]') for v in states):return 'saplings'
    raise RuntimeError('Four original spruce roots changed; no fertilizer use')


def require_growth_pose(state,root,pose):
    actual=state.get('pos',[])
    aim=next((v['aim']for v in candidates(root)if v['pose']==pose),None)
    if (state.get('health')!=20 or state.get('manual_movement') or state.get('screen') or state.get('guard_busy') or state.get('safety_hold',{}).get('active')
            or not state.get('on_ground') or state.get('flight') or len(actual)!=3
            or math.dist(actual,pose)>.75 or not body_clear(root,actual)
            or aim is None or math.dist([actual[0],actual[1]+1.62,actual[2]],aim)>=4.4):
        raise RuntimeError('Actual grounded operator is outside the proven growth stance')


def settle_growth_pose(builder,root,pose,*,seconds=3):
    """Observe the completed walk's delayed ground flag; send no movement."""
    seen=[];deadline=time.monotonic()+seconds
    while True:
        state=builder.check()
        if (state.get('health')!=20 or state.get('manual_movement')or state.get('screen')
                or state.get('guard_busy')or state.get('safety_hold',{}).get('active')
                or math.dist(state['pos'],pose)>.75):
            raise RuntimeError('Growth stance displaced or protection active; no fertilizer')
        try:require_growth_pose(state,root,pose)
        except RuntimeError:seen=[]
        else:
            if not seen or state['time']>seen[-1]:seen.append(state['time'])
            if len(seen)>=2:
                pos=state['pos'];y=round(pos[1]);assert abs(pos[1]-y)<.1
                _,rows=builder.scan([math.floor(pos[0]-.31),y-1,math.floor(pos[2]-.31)],[math.floor(pos[0]+.31),y+1,math.floor(pos[2]+.31)])
                require_ground(rows,pos);require_growth_pose(builder.check(),root,pose);return state
        if time.monotonic()>=deadline:raise RuntimeError('Grounded growth pose remains unconfirmed; no fertilizer')
        time.sleep(.08)


def require_ground(rows,pose):
    y=round(pose[1])
    for x in range(math.floor(pose[0]-.3),math.floor(pose[0]+.3-1e-7)+1):
        for z in range(math.floor(pose[2]-.3),math.floor(pose[2]+.3-1e-7)+1):
            f=rows.get((x,y-1,z),{})
            if not f.get('solid') or f.get('fluid') or f.get('block_entity'):
                raise RuntimeError('Natural dry floor is required')
            if any((x,h,z)in rows for h in (y,y+1)):
                raise RuntimeError('Operator body space is occupied')


def fertilize(builder,root,stance,book,save,*,max_uses=12):
    """Only four observed seedlings at a proven stance may receive new uses."""
    if type(max_uses)is not int or not 1<=max_uses<=12:raise ValueError('Bounded fertilizer budget required')
    def scan(low,high):return builder.scan(low,high)[1]
    def stock(item,before):
        seen=[];end=time.monotonic()+5
        while len(seen)<2:
            state=builder.check();count=inventory_counts(state)[item]
            if count==before-1:
                if not seen or state['time']>seen[-1]:seen.append(state['time'])
            elif count!=before:raise RuntimeError('Unexpected material change after original use')
            else:seen=[]
            if time.monotonic()>end:raise RuntimeError('Original use debit unknown; never retry it')
            time.sleep(.08)
        return seen
    builder.n('walk',target=stance['pose'],arrival=.1,restore_flight=False,seconds=15)
    settle_growth_pose(builder,root,stance['pose'])
    builder.n('select_item',item='minecraft:bone_meal')
    for _ in range(max_uses):
        rows=scan(root,[root[0]+1,root[1],root[2]+1])
        if growth_kind(rows,root)=='grown':break
        state=builder.check();require_growth_pose(state,root,stance['pose'])
        assert state['world_session']==book['world_session']
        before=inventory_counts(state)['minecraft:bone_meal'];assert before>0
        book['pending_effect']={'kind':'fertilize','before':before,'pose':state['pos']};save()
        reply=builder.n('interact',pos=stance['target'],face=stance['face'],expected_state=rows[tuple(stance['target'])]['state'],expected_hand='minecraft:bone_meal')
        times=stock('minecraft:bone_meal',before);book['fertilizer_receipts'].append({'request':reply['id'],'times':times});book['pending_effect']=None;save()

def grow(builder,root,plant_pose,growth_corner,path,*,max_uses=12):
    if type(max_uses)is not int or not 1<=max_uses<=12:raise ValueError('Bounded fertilizer budget required')
    path=Path(path)
    if path.exists():raise RuntimeError('Original growth journal exists; inspect it instead of replaying')
    choices=candidates(root)
    if growth_corner not in range(len(choices)):raise ValueError('Known safe diagonal corner required')
    stance=choices[growth_corner];plants=roots(root)
    book={'complete':False,'pending_effect':None,'root':root,'plant_pose':plant_pose,
          'stance':stance,'plant_receipts':[],'fertilizer_receipts':[]}
    def save():write_json(path,book)
    def scan(low,high):return builder.scan(low,high)[1]
    def stock(item,before):
        seen=[];end=time.monotonic()+5
        while len(seen)<2:
            s=builder.check();n=inventory_counts(s)[item]
            if n==before-1:
                if not seen or s['time']>seen[-1]:seen.append(s['time'])
            elif n!=before:raise RuntimeError('Unexpected material change after original use')
            else:seen=[]
            if time.monotonic()>end:raise RuntimeError('Original use debit unknown; never retry it')
            time.sleep(.08)
        return seen
    try:
        start=builder.check();book['world_session']=start['world_session'];book['inventory_before']=dict(inventory_counts(start));save()
        if inventory_counts(start)['minecraft:spruce_sapling']<8 or inventory_counts(start)['minecraft:bone_meal']<max_uses:
            raise RuntimeError('Four seeds plus four spare seeds and fertilizer required')
        low=[root[0]-3,root[1]-1,root[2]-3];high=[root[0]+4,root[1]+33,root[2]+4]
        rows=scan(low,high)
        if any(v.get('block_entity')or v.get('fluid')for v in rows.values()):raise RuntimeError('Plot includes protected storage or fluid')
        for p in plants:
            floor=rows.get((p[0],p[1]-1,p[2]),{})
            if not natural_soil(floor)or tuple(p)in rows:
                raise RuntimeError('Four empty roots on confirmed natural soil required')
            for y in range(root[1]+1,high[1]+1):
                cell=rows.get((p[0],y,p[2]))
                if cell and not ('leaves}'in cell['state']and'persistent=false'in cell['state']):raise RuntimeError('Future trunk contains existing construction or another tree')
        require_ground(rows,plant_pose);require_ground(rows,stance['pose'])
        builder.n('walk',target=plant_pose,arrival=.1,restore_flight=False,seconds=15)
        deadline=time.monotonic()+3;seen=[]
        while len(seen)<2:
            actual=builder.check()
            if actual.get('health')!=20 or actual.get('guard_busy')or actual.get('manual_movement')or actual.get('screen')or math.dist(actual['pos'],plant_pose)>.35:raise RuntimeError('Planting pose displaced; no seed use')
            velocity=actual.get('velocity',[0,0,0])
            if actual['on_ground']and not actual['flight']and math.hypot(velocity[0],velocity[2])<.02:
                if not seen or actual['time']>seen[-1]:seen.append(actual['time'])
            else:seen=[]
            if time.monotonic()>deadline:raise RuntimeError('Actual grounded planting pose remains unconfirmed; no seed use')
            time.sleep(.08)
        pos=actual['pos'];y=round(pos[1])
        assert abs(pos[1]-y)<.1
        body_rows=scan([math.floor(pos[0]-.31),y-1,math.floor(pos[2]-.31)],[math.floor(pos[0]+.31),y+1,math.floor(pos[2]+.31)])
        require_ground(body_rows,pos);book['actual_planting_pose']=pos;save()
        for p in planting_order(plants,actual['pos']):
            before=inventory_counts(builder.check())['minecraft:spruce_sapling'];book['pending_effect']={'kind':'plant','pos':p,'before':before};save()
            builder.place(p,[p[0],p[1]-1,p[2]],'up',item='minecraft:spruce_sapling',expected='Block{minecraft:spruce_sapling}[stage=0]',acceptable_states=['Block{minecraft:spruce_sapling}[stage=0]','Block{minecraft:spruce_sapling}[stage=1]'])
            times=stock('minecraft:spruce_sapling',before);book['plant_receipts'].append({'pos':p,'times':times});book['pending_effect']=None;save()
        fertilize(builder,root,stance,book,save,max_uses=max_uses)
        rows=scan(low,high);assert growth_kind(rows,root)=='grown','Known fertilizer budget exhausted; retain seedlings'
        require_growth_pose(builder.check(),root,stance['pose'])
        logs=[deepcopy(v)for v in rows.values()if v['state'].startswith('Block{minecraft:spruce_log}')]
        book.update(complete=True,stage='grown_native_harvest_pending',grown_logs=logs,inventory_after=dict(inventory_counts(builder.check())));save();return book
    except Exception as error:
        book['error']=repr(error);save();raise
