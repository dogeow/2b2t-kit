"""One ordinary, exactly consumed bone-meal use on verified natural grass."""
import time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from .acquisition import block_id,NATURAL
from .colored_sources import _protected,_stage_source


FLOWERS=frozenset('minecraft:'+name for name in ('poppy','dandelion','cornflower',
    'azure_bluet','oxeye_daisy','white_tulip','red_tulip','orange_tulip','pink_tulip',
    'allium','blue_orchid','lily_of_the_valley'))
SOFT=FLOWERS|frozenset('minecraft:'+name for name in ('short_grass','tall_grass','fern','large_fern','bush'))


def suitable(rows,pos):
    by={tuple(r['pos']):r for r in rows};x,y,z=pos;grass=by.get(tuple(pos))
    if (grass is None or block_id(grass)!='minecraft:grass_block'
            or grass.get('solid')is not True or grass.get('fluid')is not False
            or grass.get('block_entity')is not False or (x,y+1,z)in by):return False
    for r in rows:
        name=block_id(r)
        if r.get('fluid')is not False or r.get('block_entity')is not False:return False
        if name not in NATURAL|SOFT|{'minecraft:grass_block','minecraft:dirt','minecraft:coarse_dirt','minecraft:podzol'} and not name.endswith(('_log','_leaves')):
            return False
    return True


def grow(c,pos,profile,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'bone-meal-use.json'
    if path.exists():raise RuntimeError('Original flower growth intent is not replayed')
    if not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos):raise ValueError('Explicit grass coordinates required')
    if _protected(pos,profile,checkpoint()):raise RuntimeError('Flower growth overlaps a protected footprint')
    x,y,z=pos;low=[x-4,y-1,z-4];high=[x+4,y+3,z+4]
    def scan():
        checkpoint();r=c.request('scan',min=low,max=high,details=True)
        if (r.get('id')!=c.last or r.get('world_session')!=c.world or r.get('phase')!='done'
                or r.get('scan_cells_read')!=405 or r.get('scan_total_cells')!=405):raise RuntimeError('Natural flower patch scan is incomplete')
        return r['blocks']
    rows=scan()
    if not suitable(rows,pos):raise RuntimeError('Flower growth needs natural dry grass and empty space')
    _stage_source(c,pos,checkpoint)
    from work_access import approach_faces
    grass=next(r for r in rows if r['pos']==pos)
    approach_faces(c,pos,grass['state'],('up',),seconds=45)
    rows=scan()
    if not suitable(rows,pos):raise RuntimeError('Natural grass patch changed during approach')
    c.checked('select_item',item='minecraft:bone_meal')
    before=inventory_counts(checkpoint()).get('minecraft:bone_meal',0)
    if before<=16:raise RuntimeError('Keep sixteen bone meal for remaining map dyes')
    old={tuple(r['pos'])for r in rows if block_id(r)in FLOWERS}
    book={'world_session':c.world,'pos':pos,'before':before,'pending':True,'original_use_replayed':False,'inventory_credit':0};write_json(path,book)
    reply=c.checked('interact',pos=pos,face='up',expected_state=grass['state'],expected_hand='minecraft:bone_meal')
    deadline=time.monotonic()+6
    while True:
        after=inventory_counts(checkpoint()).get('minecraft:bone_meal',0)
        actual=scan()
        if after==before-1:break
        if after!=before or time.monotonic()>=deadline:raise RuntimeError('Bone meal consumption is unconfirmed; no repeat')
        time.sleep(.15)
    flowers=[r for r in actual if block_id(r)in FLOWERS and tuple(r['pos'])not in old]
    book.update(pending=False,after=after,used=1,new_flower_blocks=flowers,
                observed_flower_count=len(flowers),native_reply=reply)
    write_json(path,book);return book
