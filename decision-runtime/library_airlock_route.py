"""Use the existing two-button iron airlock without mining or enlarging the village."""
import math,time
from material_plan import inventory_counts

Z=797811
RESERVE_PATH=[[760988.5,64.,797803.5],[760988.5,64.,797809.5],[760991.5,64.,797809.5],[760991.5,64.,797811.5],[760992.5,64.,797811.5]]

def require_path(rows,points):
    for a,b in zip(points,points[1:]):
        if a[1]!=64 or b[1]!=64 or sum(a[i]!=b[i]for i in (0,2))>1:raise ValueError('Supported axis-aligned floor route required')
        for x in range(math.floor(min(a[0],b[0])),math.floor(max(a[0],b[0]))+1):
            for z in range(math.floor(min(a[2],b[2])),math.floor(max(a[2],b[2]))+1):
                floor=rows.get((x,63,z),{})
                if floor.get('solid')is not True or floor.get('fluid')is not False:raise RuntimeError('Public route floor changed')
                for y in (64,65):
                    row=rows.get((x,y,z))
                    if row and(row.get('passable')is not True or row.get('fluid')is not False):raise RuntimeError('Public route body clearance changed')

def closed(rows,x):
    return all(rows.get((x,y,Z),{}).get('state')==f'Block{{minecraft:iron_door}}[facing=west,half={half},hinge=left,open=false,powered=false]'for y,half in [(64,'lower'),(65,'upper')])

def enclosed_neighbor(scene,actor):
    """The adjacent WN09 stall cannot approach the airlock while its whole shell is closed."""
    from village_adult_enclosure import audit
    front=[760998,64,797809];box=actor.get('bounds',{});low=box.get('min',[]);high=box.get('max',[])
    if(actor.get('is_baby')is not False or actor.get('health')!=20 or len(low)!=3 or len(high)!=3
       or high[1]-low[1]<1.9 or not all(a<=lo<hi<=b for a,lo,hi,b in zip([760998,64,797806],low,high,[760999,67,797809]))):return False
    rows={tuple(v['pos']):v for v in scene.get('blocks',[])}
    return audit(rows,front=front,floor=64,inward=-1,depth=3)['verified']

def require_empty_relay(scene,door=None):
    for actor in scene.get('scan_entities',[]):
        if actor.get('type')!='minecraft:villager':continue
        box=actor['bounds']
        if box['max'][0]>760993 and box['min'][0]<760998 and box['max'][2]>Z and box['min'][2]<Z+1:
            raise RuntimeError('A villager occupies the airlock; no door interaction')
        if door is not None and math.dist(actor['pos'],[door+.5,64.,Z+.5])<3 and not enclosed_neighbor(scene,actor):
            raise RuntimeError('A villager is approaching this door; keep it closed')

def cross(builder,door,lever,destination):
    if any(r.get('pending')for r in builder.book.get('airlock_crossings',[])):raise RuntimeError('Original airlock crossing remains pending')
    from projection_completion import block_state
    other=760997 if door==760993 else 760993
    scene,rows=builder.scan([760987,63,797802],[761000,67,797813]);require_empty_relay(scene,door)
    row=rows.get((lever,64,Z),{});before=row.get('state','Block{minecraft:air}');kind,props=block_state(before)
    if(not closed(rows,door)or not closed(rows,other)or abs(lever-door)!=1
       or kind!='minecraft:lever'or props.get('face')!='floor'or props.get('powered')!='false'
       or row.get('fluid')is not False):raise RuntimeError('Both doors and the near-side floor lever must be closed/off')
    start=builder.check()['pos'];expected_start=door-.5 if destination[0]>door+.5 else door+1.5
    if abs(start[1]-64)>.12 or math.hypot(start[0]-expected_start,start[2]-(Z+.5))>.4:raise RuntimeError('Player is not at the witnessed door approach')
    for x in (math.floor(expected_start),math.floor(destination[0])):require_path(rows,[[x+.5,64.,Z+.5]]*2)
    record={'door':door,'lever':lever,'original_state':before,'pending':True};builder.book.setdefault('airlock_crossings',[]).append(record);builder.save()
    if builder.check().get('hand',{}).get('item')!='minecraft:netherite_sword':builder.n('select_item',item='minecraft:netherite_sword')
    reply=builder.n('interact',pos=[lever,64,Z],face='up',expected_state=before,expected_hand='minecraft:netherite_sword');record['lever_on_request']=reply['id'];builder.save()
    on=before.replace('powered=false','powered=true')
    deadline=time.monotonic()+4
    while True:
        _,rows=builder.scan([760992,64,Z],[760998,65,Z])
        if not closed(rows,other):raise RuntimeError('Other door changed; do not enter')
        if(rows.get((lever,64,Z),{}).get('state')==on
           and all('open=true'in rows.get((door,y,Z),{}).get('state','')for y in (64,65))):break
        if time.monotonic()>=deadline:raise RuntimeError('Held door opening not observed; no second toggle')
        time.sleep(.1)
    builder.n('walk',target=destination,arrival=.1,restore_flight=False,seconds=12)
    # Closing our still-on control is safe even if the far side changed. The
    # native expected-state check prevents a second toggle; post-close scans
    # must prove both doors closed and the relay empty before any next opening.
    reply=builder.n('interact',pos=[lever,64,Z],face='up',expected_state=on,expected_hand='minecraft:netherite_sword');record['lever_off_request']=reply['id'];builder.save()
    deadline=time.monotonic()+4
    while True:
        scene,rows=builder.scan([760992,64,Z],[760998,65,Z]);require_empty_relay(scene)
        if rows.get((lever,64,Z),{}).get('state')==before and closed(rows,door)and closed(rows,other):break
        if time.monotonic()>=deadline:raise RuntimeError('Both doors not restored after one lever-off request')
        time.sleep(.1)
    record.update(pending=False,both_doors_closed=True,lever_restored=True);builder.save()

def route(builder,destination,configuration):
    work=configuration['work_block'];source=builder.check()['pos']
    reserve=destination.uid==configuration['uuid']and list(destination.work)==work
    source_reserve=work==[760988,64,797802]and 760987<=source[0]<760990 and abs(source[1]-64)<.25 and 797803<=source[2]<797805
    if not reserve and not source_reserve:return False
    if work!=[760988,64,797802]or configuration.get('walking_airlock_verified')is not True:raise RuntimeError('No verified WN11 walking airlock route')
    if any(r.get('pending')for r in builder.book.get('airlock_crossings',[])):raise RuntimeError('Original airlock crossing remains pending')
    def walk(p):builder.n('walk',target=p,arrival=.1,restore_flight=False,seconds=20)
    if reserve and source_reserve:
        if math.dist(builder.check()['pos'],RESERVE_PATH[0])>.3:walk(RESERVE_PATH[0])
        return True
    before=inventory_counts(builder.check());scene,rows=builder.scan([760987,63,797802],[761000,67,797813]);require_path(rows,RESERVE_PATH);require_empty_relay(scene)
    if not closed(rows,760993)or not closed(rows,760997):raise RuntimeError('Airlock initially open')
    if source_reserve:
        for p in RESERVE_PATH[1:]:walk(p)
        cross(builder,760993,760992,[760994.5,64.,Z+.5]);walk([760996.5,64.,Z+.5]);cross(builder,760997,760996,[760998.5,64.,Z+.5])
    else:
        # Keep the approach inside the witnessed public gallery.
        position=builder.check()['pos'];floor=64 if position[0]<761015 else 65
        if not(760997<=position[0]<=761034 and abs(position[1]-floor)<1.2 and 797810<=position[2]<=797813):raise RuntimeError('Player outside witnessed main gallery')
        # The witnessed public aisle has a vanilla one-block/slab descent.
        # One normal walk follows it continuously; native per-step obstacle,
        # dry-floor and drop guards remain in charge of every movement tick.
        walk([760998.5,64.,Z+.5]);cross(builder,760997,760998,[760996.5,64.,Z+.5]);walk([760994.5,64.,Z+.5]);cross(builder,760993,760994,[760991.5,64.,Z+.5])
        for p in reversed(RESERVE_PATH[:-2]):walk(p)
    if inventory_counts(builder.check())!=before:raise RuntimeError('Walking airlock inventory changed')
    builder.book.setdefault('walking_district_routes',[]).append({'target':'reserve'if reserve else'main','both_doors_closed':True,'no_mining':True});builder.save();return reserve
