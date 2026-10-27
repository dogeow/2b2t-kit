"""Bounded material visits reuse Kit's AutoPlanter, rather than per-crop navigation."""
import json
import hashlib
import shutil
from pathlib import Path

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from potato_farm import FarmWait, _properties


def unresolved(registry):
    pointer = Path(registry).parent / 'native-wheat-active.json'
    if not pointer.exists():
        return False
    book = json.loads(Path(json.loads(pointer.read_text())['journal']).read_text())
    rejected=book.get('known_preflight_not_started')is True and not book.get('pending')
    rejected=rejected or(book.get('known_no_world_input')is True and not book.get('pending')
        and(book.get('no_world_input_disconnect_proof')or{}).get('classification')=='disconnected_before_any_scoped_world_input')
    from native_wheat_partial_reconcile import reconciled
    rejected=rejected or reconciled(book)
    return bool(book.get('pending') or not book.get('complete')and not rejected)


def validate_receipt(receipt, cells, before, world):
    proof = receipt.get('planter_material_batch') or {}
    expected = {tuple((p[0], p[1]+1, p[2])) for p in cells}
    counts = inventory_counts(receipt)
    if (receipt.get('phase') != 'done' or receipt.get('world_session') != world
            or proof.get('protocol') != 1 or proof.get('cells_server_confirmed') is not True
            or proof.get('total') != len(cells) or proof.get('grain_before') != before
            or any(proof.get(k) != len(cells) for k in
                   ('harvest_sent', 'removed_confirmed', 'plant_sent', 'replanted_confirmed'))
            or {tuple(p) for p in proof.get('crop_positions', [])} != expected
            or counts['minecraft:wheat'] < before + len(cells)
            or counts['minecraft:wheat_seeds'] < 4):
        raise FarmWait('WAIT_RECONCILE', 'Original native wheat batch needs its exact receipt; no replay')
    return counts


def dry_footprint(position, layout, frame):
    """A body may span several original dry farmland cells after Flight restores."""
    import math
    if (not isinstance(position,list) or len(position)!=3
            or any(type(n)not in(int,float)or not math.isfinite(n)for n in position)):
        return False
    rows={tuple(r['pos']):r for r in frame['blocks']};owned={tuple(p)for p in layout['cells']}
    y=math.floor(position[1])
    if abs(position[1]-(y+.9375))>.15:return False
    for x in range(math.floor(position[0]-.31),math.floor(position[0]+.31)+1):
        for z in range(math.floor(position[2]-.31),math.floor(position[2]+.31)+1):
            soil=rows.get((x,y,z),{})
            if ((x,y,z)not in owned or _properties(soil,'farmland','moisture',7)is None
                    or soil.get('fluid')is not False or soil.get('block_entity')is not False):return False
            for h in (y+1,y+2):
                row=rows.get((x,h,z))
                if row and (row.get('passable')is not True or row.get('fluid')is not False
                            or row.get('block_entity')is not False or h==y+2
                            or _properties(row,'wheat','age',7)is None):return False
    return True


def leave_field(c, layout, frame, out, checkpoint, book=None, journal=None):
    """Center once on nearby registered dry farmland before the vertical takeoff."""
    import math
    from .navigation import settled_state
    state=c.status();p=state['pos'];rows={tuple(r['pos']):r for r in frame['blocks']}
    candidates=[soil for soil in layout['cells']
                if _properties(rows.get(tuple(soil),{}),'farmland','moisture',7) is not None
                and rows.get(tuple(soil),{}).get('fluid') is False
                and rows.get(tuple(soil),{}).get('block_entity') is False
                and _properties(rows.get((soil[0],soil[1]+1,soil[2]),{}),'wheat','age',7) is not None
                and math.hypot(p[0]-(soil[0]+.5),p[2]-(soil[2]+.5))<=1.5
                and abs(p[1]-(soil[1]+.9375))<.3]
    if not candidates:
        raise FarmWait('WAIT_EXIT','No nearby currently observed original dry farmland footing')
    soil=min(candidates,key=lambda q:math.hypot(p[0]-(q[0]+.5),p[2]-(q[2]+.5)))
    if dry_footprint(p,layout,frame):
        return
    target=[soil[0]+.5,soil[1]+.9375,soil[2]+.5]
    intent={'world_session':c.world,'operation':'registered_farmland_exit_step','target':target,
            'before':p,'inventory_before':dict(inventory_counts(state)),'pending':True}
    out=Path(out);out.mkdir(parents=True,exist_ok=True);write_json(out/'farmland-exit.json',intent)
    if book is not None:
        book['pending']={'operation':'registered_farmland_exit_step','target':target};write_json(journal,book)
    checkpoint();reply=c.checked('walk',target=target,arrival=.15,seconds=12)
    after=settled_state(c,target,.3)
    if (reply.get('phase')!='done' or inventory_counts(after)!=inventory_counts(state)
            or not dry_footprint(after['pos'],layout,frame)):
        raise FarmWait('WAIT_EXIT','Original farmland exit step needs its exact outcome; no replay')
    write_json(out/'farmland-exit.json',{**intent,'pending':False,'phase':'done','actual':after['pos'],
               'inventory_after':dict(inventory_counts(after)),'receipt':reply})

def enter_grounded(c,layout,out,checkpoint):
    """Hand the walking planter a real dry pose, outside the registered crops."""
    import math,time
    from .fixed_tree_ground import FLOORS,prepare
    checkpoint();state=c.status()
    if state.get('on_ground')is True and state.get('flight')is False:return state
    if state.get('under_water'):raise FarmWait('WAIT_GROUND','Leave water before a wheat walking visit')
    frame=c.checked('scan',min=layout['scan_min'],max=layout['scan_max'],details=True)
    volume=1
    for a,b in zip(layout['scan_min'],layout['scan_max']):volume*=b-a+1
    if(frame.get('world_session')!=c.world or frame.get('scan_cells_read')!=volume
            or frame.get('scan_total_cells')!=volume or frame.get('unloaded_chunks',0)):
        raise FarmWait('WAIT_GROUND','Current registered-field landing scan is incomplete')
    rows={tuple(r['pos']):r for r in frame['blocks']};owned={tuple(p)for p in layout['cells']};candidates=[]
    for p,row in rows.items():
        name=row['state'].split('}',1)[0].removeprefix('Block{')
        if(p in owned or name not in FLOORS or not row.get('solid')or row.get('fluid')or row.get('block_entity')
                or p[1]+2>layout['scan_max'][1]or any((p[0],y,p[2])in rows for y in(p[1]+1,p[1]+2))):continue
        target=[p[0]+.5,float(p[1]+1),p[2]+.5]
        candidates.append((math.dist(target,state['pos']),target))
    if not candidates:raise FarmWait('WAIT_GROUND','No empty full-soil landing outside the registered crop cells')
    target=min(candidates)[1];out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/('ground-entry-'+str(time.time_ns())+'.json')
    book={'world_session':c.world,'target':target,'before':state['pos'],'pending':'grounded_planter_handoff','complete':False};write_json(path,book)
    # Cross above the chest row before descending, then use the existing dry
    # work-landing primitive. Never free-fall onto and trample mature farmland.
    height=max(state['pos'][1],target[1]+1.2)
    if height-state['pos'][1]>.1:
        checkpoint();c.checked('navigate',target=[state['pos'][0],height,state['pos'][2]],arrival=.12,air_only=True,seconds=30)
    checkpoint();c.checked('navigate',target=[target[0],height,target[2]],arrival=.12,air_only=True,seconds=30)
    checkpoint();c.checked('navigate',target=[target[0],target[1]+.15,target[2]],arrival=.1,air_only=True,seconds=30)
    actual=prepare(c,checkpoint)
    if actual.get('on_ground')is not True or actual.get('flight')is not False:
        raise FarmWait('WAIT_GROUND','Planter landing is still unconfirmed; no wheat intent created')
    book.update(complete=True,pending=None,actual=actual['pos']);write_json(path,book);return actual


def run(c, registry, layout, cells, out, checkpoint):
    if not cells or len(cells) > 16 or len({tuple(p) for p in cells}) != len(cells):
        raise ValueError('Native wheat batch requires one to sixteen distinct registered cells')
    if any(p not in layout['cells'] for p in cells):
        raise ValueError('Native wheat batch cannot expand the original field')
    if unresolved(registry):
        raise FarmWait('WAIT_RECONCILE', 'Original native wheat visit is unresolved; no new batch')
    before_state = c.status()
    before = inventory_counts(before_state)
    import math
    if any(math.dist(before_state['pos'],[p[0]+.5,p[1]+.5,p[2]+.5])>16 for p in cells):
        raise FarmWait('WAIT_REACH','Approach the scoped field before creating a native wheat intent')
    if before['minecraft:wheat_seeds'] < len(cells)+4:
        raise FarmWait('WAIT_SEED', 'Native wheat visit keeps four seeds after all scoped replants')
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    if before_state.get('flight')is True or before_state.get('on_ground')is False:
        enter_grounded(c,layout,out,checkpoint)
        before_state=c.status();before=inventory_counts(before_state)
        if any(math.dist(before_state['pos'],[p[0]+.5,p[1]+.5,p[2]+.5])>16 for p in cells):
            raise FarmWait('WAIT_REACH','Grounded entry is outside the scoped wheat reach')
        if before['minecraft:wheat_seeds']<len(cells)+4:raise FarmWait('WAIT_SEED','Grounded wheat entry lacks its seed reserve')
    journal = out/'native-wheat-batch.json'
    if journal.exists():
        old=journal.read_bytes();prior=json.loads(old)
        if prior.get('complete')is not True or prior.get('pending'):
            raise FarmWait('WAIT_RECONCILE','Previous visit in this directory is unresolved; no overwrite')
        archive=out/'completed-visits'/hashlib.sha256(old).hexdigest()[:24]
        archive.mkdir(parents=True,exist_ok=True)
        for name in ('native-wheat-batch.json','native-wheat-receipt.json',
                     'native-wheat-final-0.json','native-wheat-final-1.json','farmland-exit.json'):
            source=out/name;target_file=archive/name
            if source.exists():
                if target_file.exists()and target_file.read_bytes()!=source.read_bytes():
                    raise FarmWait('WAIT_RECONCILE','Completed wheat archive conflicts; preserve original')
                if not target_file.exists():shutil.copy2(source,target_file)
    book = {'schema': 1, 'world_session': c.world, 'registry': str(registry),
            'scope': layout, 'cells': cells, 'inventory_before': before,
            'pending': {'operation': 'planter_wheat_batch', 'soils': cells},
            'complete': False, 'controller': 'Kit.AutoPlanter', 'inventory_credit': 0}
    # Persist the exact visit before the first normal native break/use.
    write_json(journal, book)
    write_json(Path(registry).parent/'native-wheat-active.json', {'journal': str(journal.resolve())})
    checkpoint()
    receipt = c.checked('planter_wheat_batch', soils=cells, seconds=180)
    write_json(out/'native-wheat-receipt.json', receipt)
    book['native_receipt'] = {k:receipt.get(k) for k in
                             ('id','phase','time','world_session','control_revision','planter_material_batch')}
    book['pending']['receipt'] = receipt; write_json(journal, book)
    confirmed = validate_receipt(receipt, cells, before['minecraft:wheat'], c.world)
    expected = 1
    for low, high in zip(layout['scan_min'], layout['scan_max']): expected *= high-low+1
    # Two whole-visit observations, with no per-cell cruise or scan loop.
    last = receipt.get('time', 0)
    for n in range(2):
        checkpoint()
        frame = c.checked('scan', min=layout['scan_min'], max=layout['scan_max'], details=True)
        write_json(out/('native-wheat-final-%d.json'%n), frame)
        rows = {tuple(row['pos']): row for row in frame.get('blocks', [])}
        if (frame.get('phase') != 'done' or frame.get('world_session') != c.world
                or frame.get('scan_cells_read') != expected or frame.get('scan_total_cells') != expected
                or frame.get('scan_start_revision') != c.rev or frame.get('scan_end_revision') != c.rev
                or frame.get('unloaded_chunks', 0) or frame.get('time', 0) <= last
                or inventory_counts(frame) != confirmed
                or any(_properties(rows.get((p[0],p[1]+1,p[2]),{}),'wheat','age',7) is None
                       or 'minecraft:farmland' not in rows.get(tuple(p),{}).get('state','') for p in cells)):
            raise FarmWait('WAIT_RECONCILE', 'Native wheat final field/inventory observation changed; no replay')
        last = frame['time']
    leave_field(c,layout,frame,out,checkpoint,book,journal)
    after = confirmed['minecraft:wheat']
    book.update(pending=None, complete=True, inventory_after=confirmed,
                inventory_credit=after-before['minecraft:wheat'], server_cells_confirmed=True)
    write_json(journal, book)
    return {'phase': 'done', 'before': before['minecraft:wheat'], 'after': after,
            'gained': after-before['minecraft:wheat'], 'journal': str(journal),
            'registered_field_replanted': True, 'controller': 'Kit.AutoPlanter'}
