"""One lit, reversible access pit for adjacent original foundation cells.

Mining uses native sequence/server-update receipts. Model cells first use the
bounded printer; an exact zero-proposal result permits ordinary block placement
with two fresh world/stock checks. No reconnect, hold clearing, or action replay.
"""
from collections import Counter
from pathlib import Path
import math,time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_wood import cell_at
from projection_completion import block_state
from local_printing import finish_fixtures
from container_hand import select_container_hand
from projection_wood import PRE_USE_ERRORS

BRICK='Block{minecraft:stone_bricks}'
STONE='Block{minecraft:stone}'
AIR='Block{minecraft:air}'
WALL_TORCH='Block{minecraft:wall_torch}[facing=east]'
DROPS={STONE:'minecraft:cobblestone',BRICK:'minecraft:stone_bricks',
       'Block{minecraft:dirt}':'minecraft:dirt',WALL_TORCH:'minecraft:torch'}

def restore_original_ladder_after_zero(client,p,zero,out,checkpoint):
    row=zero.get('remaining')or{};wanted=row.get('expected','');name,props=block_state(wanted)
    if (zero.get('known_not_sent')is not True or zero.get('target')!=p or row.get('actual')!=AIR
            or name!='minecraft:ladder'or props.get('waterlogged')!='false'
            or props.get('facing')not in ('east','west','north','south')):
        raise RuntimeError('Exact dry original ladder and known-zero print proof required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);face=props['facing'];delta={'east':(1,0,0),'west':(-1,0,0),'north':(0,0,-1),'south':(0,0,1)}[face]
    anchor=[a-b for a,b in zip(p,delta)];support=cell_at(client,anchor);before=inventory_counts(client.status())['minecraft:ladder']
    if (before<1 or cell_at(client,p)['state']!=AIR or not support.get('solid')
            or support.get('fluid')or support.get('block_entity')
            or block_state(support['state'])[0]not in ('minecraft:stone','minecraft:stone_bricks','minecraft:oak_planks','minecraft:spruce_planks')):
        raise RuntimeError('Original ladder support or recovered item changed')
    client.checked('select_item',item='minecraft:ladder');checkpoint()
    receipt=client.request('interact',pos=anchor,face=face,expected_state=support['state'],expected_hand='minecraft:ladder');write_json(out/'native.json',receipt)
    if receipt.get('phase')!='done':raise RuntimeError('Original ladder use unconfirmed; no repeated click')
    for _ in range(2):
        checkpoint()
        if cell_at(client,p)['state']!=wanted or inventory_counts(client.status())['minecraft:ladder']!=before-1:
            raise RuntimeError('Original ladder state or stock differs; no repeated placement')
        time.sleep(.15)
    result={'target':p,'restored':True,'expected':wanted,'inventory_before':before,'inventory_after':before-1,
            'evidence_scope':'native_interact_done_and_two_fresh_world_inventory_observations','printer_known_not_sent':True}
    write_json(out/'verified.json',result);return result

def ordinary_restoration_after_zero(client,p,zero,out,checkpoint):
    if block_state((zero.get('remaining')or{}).get('expected',''))[0]=='minecraft:ladder':
        return restore_original_ladder_after_zero(client,p,zero,out,checkpoint)
    return restore_plain_brick_after_zero(client,p,zero,out,checkpoint)

def restore_plain_brick_after_zero(client,p,zero,out,checkpoint):
    """Ordinary restoration only after the printer proved it sent no proposal."""
    row=zero.get('remaining')or{}
    if (zero.get('known_not_sent')is not True or zero.get('target')!=p
            or row.get('expected')!=BRICK or row.get('actual')!=AIR):
        raise RuntimeError('Exact zero-proposal original-brick restoration proof required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    before=inventory_counts(client.status())['minecraft:stone_bricks']
    if before<1 or cell_at(client,p)['state']!=AIR:raise RuntimeError('Restoration material or empty cell changed')
    client.checked('select_item',item='minecraft:stone_bricks')
    faces={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'west':(-1,0,0),'east':(1,0,0)}
    passive={'minecraft:stone','minecraft:stone_bricks','minecraft:chiseled_stone_bricks','minecraft:iron_ore','minecraft:dirt','minecraft:smooth_quartz','minecraft:quartz_block','minecraft:spruce_planks','minecraft:oak_planks'}
    for face,delta in faces.items():
        checkpoint();anchor=[a-b for a,b in zip(p,delta)];actual=cell_at(client,anchor)
        if block_state(actual['state'])[0]not in passive or not actual.get('solid')or actual.get('fluid')or actual.get('block_entity'):continue
        if cell_at(client,p)['state']!=AIR or inventory_counts(client.status())['minecraft:stone_bricks']!=before:
            raise RuntimeError('Cell or stock changed before ordinary restoration')
        receipt=client.request('interact',pos=anchor,face=face,expected_state=actual['state'],expected_hand='minecraft:stone_bricks')
        write_json(out/('native-'+face+'.json'),receipt)
        if receipt.get('phase')=='error'and receipt.get('detail')in PRE_USE_ERRORS:continue
        if receipt.get('phase')!='done':raise RuntimeError('Ordinary restoration outcome unknown; no further use')
        for _ in range(2):
            checkpoint()
            if cell_at(client,p)['state']!=BRICK or inventory_counts(client.status())['minecraft:stone_bricks']!=before-1:
                raise RuntimeError('Ordinary restoration world/stock mismatch; no repeated use')
            time.sleep(.15)
        proof={'target':p,'restored':True,'inventory_before':before,'inventory_after':before-1,
               'evidence_scope':'native_interact_done_and_two_fresh_world_inventory_observations',
               'printer_known_not_sent':True,'native_request_id':receipt.get('id')}
        write_json(out/'verified.json',proof);return proof
    raise RuntimeError('No visible passive support for the original brick')

def finish_entry_floor(client,pit,out,checkpoint,offset_x=0):
    """Print a recovered floor from beside the opening, outside its player box."""
    out=Path(out);out.mkdir(parents=True,exist_ok=False);x,y,z=pit
    checkpoint();rows=client.request('scan',min=[x-1,y-1,z-1],max=[x+1,y+2,z+1],details=True)['blocks']
    cells={tuple(r['pos']):r for r in rows}
    if cells.get((x,y-1,z),{}).get('state')!=STONE or cells.get(tuple(pit)):
        raise RuntimeError('Recovered natural stone and an empty entry floor are required')
    poses=[]
    for dx,dz in ((0,-1),(1,0),(0,1),(-1,0)):
        if (cells.get((x+dx,y,z+dz),{}).get('state')==BRICK
                and all((x+dx,yy,z+dz)not in cells for yy in (y+1,y+2))):
            poses.append([x+.5+offset_x+dx,y+1.2,z+.5+dz])
    if not poses:raise RuntimeError('No unchanged adjacent floor and clear standing space')
    pose=poses[0];write_json(out/'adjacent-pose.json',{'target':pose,'floor':pit,'pending':True})
    client.checked('navigate',target=pose,arrival=.15,air_only=True,seconds=20);checkpoint()
    write_json(out/'adjacent-pose.json',{'target':pose,'actual':client.status()['pos'],'floor':pit,'pending':False})
    hand=select_container_hand(client)
    client.checked('interact',pos=[x,y-1,z],face='up',expected_state=STONE,expected_hand=hand)
    if cell_at(client,pit)['state']!=AIR:raise RuntimeError('Entry floor changed before printing')
    result=finish_fixtures(client,[pit],seconds=8,approach=False)
    write_json(out/'floor-print-result.json',result)
    if result and result[0].get('result')=='unresolved'and result[0].get('known_not_sent')is True:
        return restore_plain_brick_after_zero(client,pit,result[0],out/'ordinary-after-known-zero',checkpoint)
    if not result or result[0].get('result')!='matched':raise RuntimeError('Adjacent entry floor print remains unplaced; no replay')
    return result

def validate(model,scan,plan):
    pit=plan['pit'];expected={tuple(r['pos']):r['state']for r in model['expected']}
    cells={tuple(r['pos']):r for r in scan}
    if (len(pit)!=3 or any(type(v)is not int for v in pit)
            or pit[1]!=model['bounds']['min'][1]
            or model.get('loaded_chunks_verified')is not True):
        raise RuntimeError('A complete model and its lowest foundation layer are required')
    positions=plan['goals']+plan.get('temporary',[])+[pit]
    if len({tuple(p)for p in positions})!=len(positions):raise RuntimeError('Pit cells overlap')
    for p in positions:
        if (any(type(v)is not int for v in p)or p[1]not in range(pit[1],pit[1]+3)
                or max(abs(p[i]-pit[i])for i in (0,2))>1):
            raise RuntimeError('Pit only supports adjacent cells in three bounded layers')
        row=cells.get(tuple(p));wanted=expected.get(tuple(p))
        if not row or row.get('fluid')is not False or row.get('block_entity')is not False:
            raise RuntimeError('Pit work has unknown, wet, or container cells')
        if p in plan['goals']:
            if wanted!=BRICK or row['state']not in (STONE,'Block{minecraft:dirt}',BRICK):
                raise RuntimeError('Foundation target changed or is not original stone brick')
        elif row['state']!=wanted or (wanted!=BRICK and block_state(wanted or'')[0]!='minecraft:ladder'):
            raise RuntimeError('Temporary cell is not an unchanged original brick or ladder')
    x,y,z=pit
    for yy in (y-2,y-1):
        row=cells.get((x,yy,z),{})
        if row.get('state')!=STONE or row.get('solid')is not True or row.get('fluid')is not False or row.get('block_entity')is not False:
            raise RuntimeError('Pit requires two proved dry natural stone blocks below its floor')
    # The floor/support pair, every mined cell, and adjacent water are known.
    removed=[*positions,[x,y-1,z]]
    for p in removed:
        for dx,dy,dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
            if cells.get((p[0]+dx,p[1]+dy,p[2]+dz),{}).get('fluid')is True:
                raise RuntimeError('Water beside the access or foundation must be preserved')
    for yy in (y+1,y+2):
        row=cells.get((x,yy,z))
        if row and block_state(row['state'])[0]!='minecraft:ladder':
            raise RuntimeError('Original furniture obstructs the pit entrance')
    return expected,cells

def run(client,model,plan,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    pit=plan['pit'];x,y,z=pit;key=model['placement_key'];world=client.world
    def state():
        checkpoint();q=client.status()
        if q['world_session']!=world or q.get('projection_selection',{}).get('key')!=key:
            raise RuntimeError('Foundation world or original model changed')
        return q
    low=[x-2,y-3,z-2];high=[x+2,y+4,z+2]
    scan=client.request('scan',min=low,max=high,details=True)
    if scan.get('phase')!='done' or scan.get('world_session')!=world:raise RuntimeError('Complete current pit scan required')
    expected,cells=validate(model,scan['blocks'],plan)
    goals=[p for p in plan['goals']if cells[tuple(p)]['state']!=BRICK]
    if not goals:return {'complete':True,'already_matched':True,'placed':0}
    temp=[pit]+plan.get('temporary',[])
    baseline=inventory_counts(state());reserve=sum(expected[tuple(p)]==BRICK for p in temp)
    if baseline['minecraft:stone']<1 or baseline['minecraft:torch']<1 or baseline['minecraft:stone_bricks']<reserve:
        raise RuntimeError('Carried natural backfill, light, and original shell reserve required')
    if not any(r.get('item')=='minecraft:diamond_pickaxe'and r.get('durability',0)>100
               and not any(e.get('id')=='minecraft:silk_touch'for e in r.get('enchantments',[]))for r in state()['inventory']):
        raise RuntimeError('A non-Silk-Touch pickaxe with a bounded durability reserve is required')
    book={'world_session':world,'placement_key':key,'model_hash':model['content_hash'],
          'pit':pit,'goals':goals,'temporary':temp,'pending':None,'mined':[],
          'restored':[],'inventory_before':dict(baseline),'complete':False,'stone_backfill_required':True,'light_required':False}
    path=out/'pit-journal.json'
    def save():write_json(path,book)
    save()
    def observe(p,wanted):
        for _ in range(2):
            if cell_at(client,p)['state']!=wanted:raise RuntimeError('Exact pit cell did not settle; no repeated action')
            state();time.sleep(.15)
    def move(point,label):
        state();book['pending']={'kind':'native_collision_checked_move','target':point,'label':label};save()
        try:r=client.checked('navigate',target=point,arrival=.15,air_only=True,seconds=25)
        finally:book['pending']['request_id']=client.last;save()
        write_json(out/(label+'-native.json'),r)
        if math.dist(state()['pos'],point)>.4:raise RuntimeError('Pit pose not physically confirmed')
        book['pending']=None;save()
    px=x+.5+plan.get('offset_x',0);pz=z+.5
    if max(abs(state()['pos'][0]-px),abs(state()['pos'][2]-pz))>.35 or abs(state()['pos'][1]-(y+1.2))>.4:
        raise RuntimeError('Caller must first reach the proved pit entrance')
    drops=Counter()
    def mine(p,face,purpose):
        row=cell_at(client,p);source=row['state'];name=block_state(source)[0]
        drop='minecraft:ladder'if name=='minecraft:ladder'else DROPS.get(source)
        if drop is None or row.get('fluid')or row.get('block_entity'):
            raise RuntimeError('Unknown or protected mining result; no action sent')
        client.checked('select_item',item='minecraft:diamond_pickaxe')
        hand=state()['hand']
        if (hand.get('item')!='minecraft:diamond_pickaxe'or hand.get('durability',0)<32
                or any(e.get('id')=='minecraft:silk_touch'for e in hand.get('enchantments',[]))):
            raise RuntimeError('Unexpected Silk Touch tool; drop balance is not valid')
        book['pending']={'kind':'one_native_mine','pos':p,'before':source,'purpose':purpose};save()
        try:r=client.checked('mine_block',pos=p,face=face,expected_state=source,seconds=20)
        finally:native_id=client.last;book['pending']['request_id']=native_id;save()
        write_json(out/('mine-%03d-native.json'%len(book['mined'])),r);observe(p,AIR)
        drops[drop]+=1;book['mined'].append({'pos':p,'before':source,'drop':drop,'purpose':purpose,'native_request':native_id});book['pending']=None;save()
    # Remove a planned ladder explicitly before changing its attachment block.
    ladders=[p for p in temp if block_state(expected[tuple(p)])[0]=='minecraft:ladder']
    for p in ladders:mine(p,'up','temporary_original_ladder')
    mine(pit,'up','temporary_original_floor');mine([x,y-1,z],'up','natural_access_stone')
    move([px,y-1+.2,pz],'pit-down')
    anchor=[x-1,y-1,z];support=cell_at(client,anchor)
    if not support.get('solid')or support.get('fluid')or support.get('block_entity'):raise RuntimeError('Pit lamp support changed')
    client.checked('select_item',item='minecraft:torch');book['pending']={'kind':'one_wall_torch','pos':[x,y-1,z]};save()
    try:r=client.checked('interact',pos=anchor,face='east',expected_state=support['state'],expected_hand='minecraft:torch')
    finally:book['pending']['request_id']=client.last;save()
    write_json(out/'wall-torch-native.json',r);observe([x,y-1,z],WALL_TORCH)
    if inventory_counts(state())['minecraft:torch']!=baseline['minecraft:torch']-1:raise RuntimeError('Pit light stock not confirmed')
    book.update(pending=None,light_required=True);save()
    def face(p):
        if p[0]<x:return'east'
        if p[0]>x:return'west'
        return'south'if p[2]<z else'north'
    rest=[p for p in temp if p!=pit and p not in ladders]
    for p in sorted(rest,key=lambda p:(p[1],abs(p[0]-x)+abs(p[2]-z))):
        mine(p,'down'if p[1]>y+1 else face(p),'temporary_original_shell')
    for p in sorted(goals,key=lambda p:(-p[1],abs(p[0]-x)+abs(p[2]-z))):mine(p,face(p),'original_foundation_repair')
    desired={item:baseline[item]+n for item,n in drops.items()}
    desired['minecraft:torch']=baseline['minecraft:torch']-1
    def have_drops():return all(inventory_counts(state())[item]==count for item,count in desired.items())
    deadline=time.monotonic()+6
    while not have_drops()and time.monotonic()<deadline:time.sleep(.15)
    if not have_drops():
        for i,(dx,dz)in enumerate(((.35,.35),(.65,.35),(.65,.65),(.35,.65))):
            move([x+dx,y-1+.2,z+dz],'pickup-margin-%d'%i)
            if have_drops():break
        move([px,y-1+.2,pz],'working-pose-restored')
    if not have_drops():raise RuntimeError('Actual drops remain uncollected; do not fill the pit or credit them')
    write_json(out/'actual-mining-drop-balance.json',{'before':dict(baseline),'expected_after_mining':desired,'actual':dict(inventory_counts(state()))})
    if inventory_counts(state())['minecraft:stone_bricks']<reserve+len(goals):raise RuntimeError('Restore reserve changed after pickup')
    def printed(p,purpose):
        book['pending']={'kind':'one_bounded_projection_print','pos':p,'purpose':purpose};save()
        result=finish_fixtures(client,[p],seconds=8,approach=False)
        if (block_state(expected[tuple(p)])[0]in ('minecraft:stone_bricks','minecraft:ladder')and result
                and result[0].get('result')=='unresolved'and result[0].get('known_not_sent')is True):
            ordinary_restoration_after_zero(client,p,result[0],out/('ordinary-restore-'+','.join(map(str,p))),state)
            observe(p,expected[tuple(p)]);book['pending']=None;book['restored'].append({'pos':p,'purpose':purpose,'ordinary_after_known_zero':True});save();return
        if not result or result[0].get('result')!='matched':
            book['pending']=None;book['known_unplaced_result']=result;save()
            raise RuntimeError('Bounded pit print did not complete; retain known outcome')
        observe(p,expected[tuple(p)]);book['pending']=None;book['restored'].append({'pos':p,'purpose':purpose});save()
    def order(p):return(-p[1],-math.hypot(p[0]+.5-px,p[2]+.5-pz))
    for p in sorted(goals,key=order):printed(p,'original_foundation_repair')
    for p in sorted((p for p in temp if p!=pit),key=order):printed(p,'original_shell_restore')
    mine([x,y-1,z],'up','recover_owned_temporary_light')
    deadline=time.monotonic()+5
    while inventory_counts(state())['minecraft:torch']!=baseline['minecraft:torch']and time.monotonic()<deadline:time.sleep(.15)
    if inventory_counts(state())['minecraft:torch']!=baseline['minecraft:torch']:raise RuntimeError('Temporary light not recovered')
    book['light_required']=False;save();move([px,y+1.2,pz],'pit-exit-above')
    support=cell_at(client,[x,y-2,z]);stone_before=inventory_counts(state())['minecraft:stone']
    if support['state']!=STONE or cell_at(client,[x,y-1,z])['state']!=AIR:raise RuntimeError('Natural backfill precondition changed')
    client.checked('select_item',item='minecraft:stone');book['pending']={'kind':'one_ordinary_natural_stone_restore','pos':[x,y-1,z]};save()
    try:r=client.checked('interact',pos=[x,y-2,z],face='up',expected_state=STONE,expected_hand='minecraft:stone')
    finally:book['pending']['request_id']=client.last;save()
    write_json(out/'ordinary-natural-stone-native.json',r);observe([x,y-1,z],STONE)
    if inventory_counts(state())['minecraft:stone']!=stone_before-1:raise RuntimeError('Natural backfill stock mismatch')
    book.update(pending=None,stone_backfill_required=False);save()
    finish_entry_floor(client,pit,out/'entry-floor-from-adjacent',state,plan.get('offset_x',0))
    book['restored'].append({'pos':pit,'purpose':'original_floor_restore_from_adjacent'});save()
    for p in goals+temp:observe(p,expected[tuple(p)])
    final=inventory_counts(state())
    if (final['minecraft:stone_bricks']!=baseline['minecraft:stone_bricks']-len(goals)
            or final['minecraft:stone']!=baseline['minecraft:stone']-1
            or final['minecraft:torch']!=baseline['minecraft:torch']
            or final['minecraft:ladder']!=baseline['minecraft:ladder']):
        raise RuntimeError('Final foundation/backfill/light balances differ')
    book.update(complete=True,pending=None,actual_inventory=dict(final),placed=len(goals));save()
    return {'complete':True,'placed':len(goals),'journal':str(path),'natural_stone_backfilled':True,'light_recovered':True}


def resume_known_print_refusal(client,model,source,out,checkpoint):
    """Finish an exactly journaled, mined pit after a proved zero-proposal print."""
    import json
    source=Path(source);old=json.loads(source.read_text());out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if (old.get('pending')is not None or old.get('complete')is not False
            or old.get('world_session')!=client.world or old.get('placement_key')!=model['placement_key']
            or old.get('model_hash')!=model['content_hash']
            or not old.get('known_unplaced_result')or old['known_unplaced_result'][0].get('known_not_sent')is not True):
        raise RuntimeError('Only an intact same-world known-zero pit journal may continue')
    before=old.get('inventory_before')
    if not isinstance(before,dict):raise RuntimeError('Original native inventory baseline required')
    pit=old['pit'];x,y,z=pit;offset=client.status()['pos'][0]-(x+.5)
    if abs(offset)>.2 or abs(client.status()['pos'][2]-(z+.5))>.2:raise RuntimeError('Actor left the known pit')
    expected={tuple(r['pos']):r['state']for r in model['expected']}
    mined_positions={tuple(r['pos'])for r in old['mined']}
    for p in old['goals']:
        actual=cell_at(client,p)['state']
        if (actual not in (AIR,expected[tuple(p)])or actual==AIR and tuple(p)not in mined_positions):
            raise RuntimeError('Original goal is not its matched state or its confirmed mined air')
    book={'world_session':client.world,'placement_key':model['placement_key'],'source':str(source),
          'original_mining_replayed':False,'pending':None,'complete':False,'continued_temp_cells':[],'continued_goal_cells':[]}
    path=out/'continuation-journal.json'
    def save():write_json(path,book)
    save()
    def observe(p,wanted):
        for _ in range(2):
            checkpoint()
            if cell_at(client,p)['state']!=wanted:raise RuntimeError('Continued cell changed; no replay')
            time.sleep(.15)
    for p in sorted(old['goals'],key=lambda p:(-p[1],-math.hypot(p[0]-x,p[2]-z))):
        wanted=expected[tuple(p)]
        if cell_at(client,p)['state']==wanted:continue
        prior=old['known_unplaced_result'][0]
        if wanted==BRICK and prior.get('target')==p:
            restore_plain_brick_after_zero(client,p,prior,out/('ordinary-goal-'+','.join(map(str,p))),checkpoint)
        else:
            result=finish_fixtures(client,[p],seconds=8,approach=False)
            write_json(out/('goal-%03d.json'%len(book['continued_goal_cells'])),result)
            if wanted==BRICK and result and result[0].get('known_not_sent')is True:
                restore_plain_brick_after_zero(client,p,result[0],out/('ordinary-goal-'+','.join(map(str,p))),checkpoint)
            elif not result or result[0].get('result')!='matched':raise RuntimeError('Continued original goal remains unplaced')
        observe(p,wanted);book['continued_goal_cells'].append(p);save()
    for p in sorted((p for p in old['temporary']if p!=pit),key=lambda p:(-p[1],-math.hypot(p[0]-x,p[2]-z))):
        actual=cell_at(client,p)['state'];wanted=expected[tuple(p)]
        if actual==wanted:continue
        if actual!=AIR:raise RuntimeError('Temporary cell changed since known print refusal')
        prior=old['known_unplaced_result'][0]
        if block_state(wanted)[0]in ('minecraft:stone_bricks','minecraft:ladder')and prior.get('target')==p:
            ordinary_restoration_after_zero(client,p,prior,out/('ordinary-restore-'+','.join(map(str,p))),checkpoint)
            observe(p,wanted);book['continued_temp_cells'].append(p);save();continue
        result=finish_fixtures(client,[p],seconds=8,approach=False);write_json(out/('restored-%03d.json'%len(book['continued_temp_cells'])),result)
        if (block_state(wanted)[0]in ('minecraft:stone_bricks','minecraft:ladder')and result and result[0].get('result')=='unresolved'
                and result[0].get('known_not_sent')is True):
            ordinary_restoration_after_zero(client,p,result[0],out/('ordinary-restore-'+','.join(map(str,p))),checkpoint)
            observe(p,wanted);book['continued_temp_cells'].append(p);save();continue
        if not result or result[0].get('result')!='matched':raise RuntimeError('Continued print still unplaced; retain known outcome')
        observe(p,wanted);book['continued_temp_cells'].append(p);save()
    lamp=[x,y-1,z]
    if old['light_required']:
        observe(lamp,WALL_TORCH);client.checked('select_item',item='minecraft:diamond_pickaxe')
        book['pending']={'kind':'recover_original_temporary_light','pos':lamp};save()
        try:r=client.checked('mine_block',pos=lamp,face='up',expected_state=WALL_TORCH,seconds=20)
        finally:book['pending']['request_id']=client.last;save()
        write_json(out/'light-recovery-native.json',r);observe(lamp,AIR);book['pending']=None;save()
        until=time.monotonic()+5
        while inventory_counts(client.status())['minecraft:torch']!=before['minecraft:torch']and time.monotonic()<until:checkpoint();time.sleep(.15)
        if inventory_counts(client.status())['minecraft:torch']!=before['minecraft:torch']:raise RuntimeError('Original lamp not recovered')
    if old['stone_backfill_required']:
        observe(lamp,AIR);checkpoint()
        client.checked('navigate',target=[x+.5+offset,y+1.2,z+.5],arrival=.15,air_only=True,seconds=20)
        observe([x,y-2,z],STONE);client.checked('select_item',item='minecraft:stone')
        book['pending']={'kind':'one_ordinary_original_stone_backfill','pos':lamp};save()
        try:r=client.checked('interact',pos=[x,y-2,z],face='up',expected_state=STONE,expected_hand='minecraft:stone')
        finally:book['pending']['request_id']=client.last;save()
        write_json(out/'natural-backfill-native.json',r);observe(lamp,STONE);book['pending']=None;save()
    else:observe(lamp,STONE)
    finish_entry_floor(client,pit,out/'entry-floor',checkpoint,offset)
    for p in old['goals']+old['temporary']:observe(p,expected[tuple(p)])
    stock=inventory_counts(client.status())
    if (stock['minecraft:stone_bricks']!=before['minecraft:stone_bricks']-len(old['goals'])
            or stock['minecraft:stone']!=before['minecraft:stone']-1
            or stock['minecraft:torch']!=before['minecraft:torch']
            or stock['minecraft:ladder']!=before.get('minecraft:ladder',0)):
        raise RuntimeError('Continued pit inventory does not match its original baseline')
    book.update(complete=True,pending=None,actual_inventory=dict(stock),placed=len(old['goals']));save()
    return {'complete':True,'placed':len(old['goals']),'journal':str(path),'original_mining_replayed':False}
