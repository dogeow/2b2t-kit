"""Prove dry breathing before an owned material controller releases its lease.

Physical water cells, not only the cached under_water boolean, decide whether
return is needed. Never send cleanup past a manual handoff or unknown request.
"""
import math,time
from pathlib import Path
from kit_runtime.journal import write_json
from .construction_breathing import _owned,vertical_air_target
from .protocol import JobBlocked,JobPaused


def before_release(c):
    if (getattr(c,'native_inflight',None)is not None
            or getattr(c,'unconfirmed_native_request',None)is not None):
        raise JobBlocked('Native request unresolved; no lease release or recovery replay')
    state=c.status(wait_interface=False)
    if not _owned(c,state):
        # Let the native exact-owner release check reject a foreign owner.
        # In particular, never close a human UI or move after takeover.
        return
    x,y,z=state['pos']
    if y>=320 and state.get('under_water')is not True:return
    low=[math.floor(x-.31),math.floor(y),math.floor(z-.31)]
    high=[math.floor(x+.31),min(319,math.floor(y)+13),math.floor(z+.31)]
    frame=c.request('scan',min=low,max=high,details=True)
    if (frame.get('phase')!='done'or frame.get('world_session')!=c.world
            or frame.get('scan_cells_read')!=math.prod(b-a+1 for a,b in zip(low,high))
            or frame.get('scan_total_cells')!=frame.get('scan_cells_read')
            or type(frame.get('scan_start_revision'))is not int
            or frame.get('scan_start_revision')!=frame.get('scan_end_revision')):
        raise JobBlocked('Current breathing column unconfirmed; no lease release')
    water={'Block{minecraft:water}[level='+str(n)+']'for n in range(16)}
    wet=state.get('under_water')is True or any(v.get('state')in water and v['pos'][1]<=math.floor(y+1.8)
            for v in frame.get('blocks',[]))
    if not wet:return
    path=Path(c.out)/('release-breathing-'+str(time.time_ns())+'.json')
    book={'world_session':c.world,'task_session':c.task,'from':state['pos'],
          'cached_under_water':state.get('under_water'),'physical_water_observed':True,
          'pending':None,'complete':False,'lease_released':False,'resource_actions_replayed':False}
    write_json(path,book)
    current=c.status(wait_interface=False)
    if not _owned(c,current)or math.dist(current['pos'],state['pos'])>.2:
        raise JobPaused('Water observation lost its exact owner or position; no recovery input')
    target=vertical_air_target(state['pos'],frame,c.world)
    if (target is None or current.get('health',0)<19 or current.get('air_supply',0)<245
            or current.get('oxygen_bonus',0)<3 or not current.get('auto_log')or not current.get('flight')):
        book['reason']='no verified healthy vertical return';write_json(path,book)
        raise JobBlocked('Breathing return not eligible; retain native protection without releasing underwater')
    # Ordinary navigation can settle within .7 blocks. Reserve 1.5 above the
    # actual water surface instead of returning to a marginal dry-foot target.
    floor=math.floor(target[1]);target[1]=floor+1.5;book['target']=target
    if floor+3>high[1]or any(floor<=v['pos'][1]<=floor+3 and v.get('state')!='Block{minecraft:air}'for v in frame['blocks']):
        raise JobBlocked('Full dry return headroom not observed; no release or guessed ascent')
    if current.get('under_water'):
        c.checked('air_return_set',target=target)
    book['pending']='one_verified_vertical_return';write_json(path,book)
    try:reply=c.request('navigate',target=target,arrival=.5,air_only=False,seconds=20)
    finally:book['request_id']=getattr(c,'last',None);write_json(path,book)
    if reply.get('phase')!='done':
        raise JobBlocked('Original breathing return not confirmed; no second navigation or release')
    book['pending']='fresh_dry_and_full_air_confirmation';write_json(path,book)
    stamps=[];deadline=time.monotonic()+6
    while len(stamps)<2:
        fresh=c.request('snapshot')
        if not _owned(c,fresh):raise JobPaused('Control changed after breathing return; no release')
        stamp=fresh.get('time');maximum=fresh.get('max_air_supply',300)
        good=(type(stamp)is int and fresh.get('under_water')is False
              and fresh.get('air_supply',0)>=maximum and fresh.get('health',0)>=19
              and fresh['pos'][1]>=target[1]-.7 and math.dist(fresh['pos'],target)<=.8)
        if good and(not stamps or stamp>stamps[-1]):stamps.append(stamp)
        elif not good:stamps=[]
        if time.monotonic()>deadline:
            raise JobBlocked('Dry breathing or full oxygen still unconfirmed; no lease release')
        time.sleep(.1)
    book.update(pending=None,complete=True,dry_frames=stamps,actual_pos=fresh['pos'],actual_air=fresh['air_supply'])
    write_json(path,book)
