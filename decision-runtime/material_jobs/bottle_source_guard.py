"""One bounded normal PvE clearance after a proved pre-dispatch bottle refusal."""
import math
import time
from pathlib import Path

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from .protocol import JobBlocked

REFUSAL='Water bottle action requires the current healthy idle guarded material lease'


def clear_drowned(backend,original_before,*,sleep=time.sleep,clock=time.monotonic):
    c=backend.ensure_client();terminal=getattr(c,'last_terminal_evidence',{})or{};q=c.status()
    if (terminal.get('op')!='bottle_fill' or terminal.get('phase')!='error' or terminal.get('detail')!=REFUSAL
            or terminal.get('request_id')!=getattr(c,'last',None) or terminal.get('world_session')!=c.world
            or terminal.get('task_session')!=getattr(c,'task',None)
            or getattr(c,'native_inflight',None)is not None or getattr(c,'unconfirmed_native_request',None)is not None
            or inventory_counts(q)!=inventory_counts(original_before)):
        return False
    cfg=backend.profile.get('mud_bucket_source')or{};source=cfg.get('pos');stand=cfg.get('approach')
    def healthy(state):
        return (state.get('world_session')==c.world and state.get('health')==20 and state.get('food',0)>=18
            and state.get('flight')is True and state.get('guard_armed')is True and state.get('guard_pve_only')is True
            and state.get('kill_aura')is True and not state.get('under_water')and not state.get('manual_movement')
            and not state.get('screen')and state.get('recent_hurt_at')==original_before.get('recent_hurt_at'))
    if not healthy(q)or not source or not stand or math.dist(q['pos'],stand)>.6:return False
    x,y,z=q['pos'];low=[math.floor(x-17),math.floor(y-17),math.floor(z-17)];high=[math.floor(x+17),math.floor(y+19),math.floor(z+17)]
    def enemies():
        scan=c.checked('scan',min=low,max=high,details=True)
        if scan.get('world_session')!=c.world or not isinstance(scan.get('scan_entities'),list):
            raise JobBlocked('Source hostile envelope was not completely observed')
        return[e for e in scan['scan_entities']if e.get('alive')and e.get('hostile')and e.get('health',0)>0]
    threats=enemies()
    if (not threats or any(e.get('type')!='minecraft:drowned'or e.get('has_custom_name')is not False
            or e.get('visible')is not True or math.hypot(e['pos'][0]-x,e['pos'][2]-z)>5
            or not source[1]-5<=e['pos'][1]<=source[1]+1 for e in threats)):
        return False
    out=Path(c.out)/('source-pve-'+terminal['request_id']);out.mkdir(exist_ok=False)
    book={'world_session':c.world,'original_refusal':terminal,'observed_drowned':threats,'pending':'normal_sword_approach','complete':False}
    write_json(out/'clearance.json',book)
    backend.checkpoint();c.checked('select_item',item='minecraft:netherite_sword')
    c.checked('navigate',target=[x,source[1]+1.2,z],arrival=.2,air_only=True,seconds=30)
    deadline=clock()+25
    while True:
        state=c.status(wait_interface=False)
        if not healthy(state):raise JobBlocked('Source PvE health, control or guard changed; no bottle retry')
        nearby=[e for e in state.get('entities',[])if e.get('uuid')in{v['uuid']for v in threats}and e.get('health',0)>0]
        if not nearby and not state.get('guard_busy'):break
        if clock()>=deadline:raise JobBlocked('Source drowned clearance still unproved; no bottle retry')
        sleep(.25)
    if enemies():raise JobBlocked('Source hostile envelope remains occupied; no bottle retry')
    c.checked('navigate',target=stand,arrival=.2,air_only=True,seconds=30)
    if not healthy(c.status()):raise JobBlocked('Source return protection changed')
    book.update(pending=None,complete=True,health=20,ordinary_hostile_only_aura=True,bottle_use_replayed=False)
    write_json(out/'clearance.json',book);return True
