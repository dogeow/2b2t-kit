"""Shared projection-build helpers: material stock, supply options and the native safety heartbeat.

The model-driven supervisor (Jev) that used to live here was removed on 2026-11-28; Kit's native
projection job and its safety leases are unchanged.
"""
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid

TERMINAL={'complete','manual_stop','world_changed','placement_changed','needs_review'}

class SafetyHeartbeat:
    def __init__(self,root,world_session):
        self.root=Path(root);self.world=world_session;self.id='jev-owner-'+uuid.uuid4().hex[:16]
        self.stop=threading.Event();self.thread=None;self.attached=False;self.last_poll=time.monotonic()
    def write(self,finished=False):
        path=self.root/('supervision-heartbeat-'+self.id+'.json');temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps({'id':self.id,'world_session':self.world,'time':int(time.time()*1000),'finished':finished}));temp.replace(path)
    def touch(self):self.last_poll=time.monotonic()
    def start(self):
        self.write()
        def loop():
            while not self.stop.wait(2):
                if time.monotonic()-self.last_poll>10:return # A hung control loop must not renew its lease.
                try:self.write()
                except OSError:return # Native watchdog handles a lost heartbeat.
        self.thread=threading.Thread(target=loop,name='kit-native-safety-heartbeat',daemon=True);self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=3)
        if self.attached:
            try:self.write(finished=True)
            except OSError:pass # Native expiry remains the fallback.

def fingerprint(s):
    b=s['build_job'];p=s.get('professional_printer',{})
    kind='server_wait' if p.get('waiting_for_server') else 'materials' if b.get('material_deficits') else 'navigation' if b.get('blocked_blocks',0) else 'placement'
    value={'kind':kind,'outcome':b.get('outcome'),'phase':b.get('phase'),'auto_move':b.get('auto_move'),
           'deficits':sorted(b.get('material_deficits',{}))[:8],'bridge':s.get('bridge_version'),'kit_version':s.get('kit_version'),
           'server_scope':hashlib.sha256(str(s.get('server')).lower().removesuffix(':25565').encode()).hexdigest()[:12]}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()[:20],value

def stocks(s):
    result={}
    for item in s.get('inventory',[]):
        if 0<=item.get('slot',-1)<36:result[item['item']]=result.get(item['item'],0)+item['count']
    return result

def room_for(s,item):
    slots=[entry for entry in s.get('inventory',[]) if 0<=entry.get('slot',-1)<36]
    if len(slots)!=36:return 0 # Incomplete observations cannot authorize inventory mutations.
    if any(entry.get('count',0)==0 or entry.get('item')=='minecraft:air' for entry in slots):return 64
    return sum(max(0,entry.get('max_stack',64)-entry['count']) for entry in slots if entry['item']==item)

def plank_option(s):
    inventory=stocks(s)
    for item,count in sorted(s.get('build_job',{}).get('material_needs',{}).items()):
        if item.endswith('_planks') and inventory.get(item,0)<count and inventory.get(item.replace('_planks','_log'),0)>0 and room_for(s,item)>=4:return item
    return None

def supply_options(s):
    inventory=stocks(s);wanted={item for item,count in s.get('build_job',{}).get('material_needs',{}).items() if inventory.get(item,0)<count}
    for item,count in s.get('build_job',{}).get('material_needs',{}).items():
        if item.endswith('_planks') and inventory.get(item.replace('_planks','_log'),0)<(max(0,count-inventory.get(item,0))+3)//4:wanted.add(item.replace('_planks','_log'))
    return [candidate for candidate in s.get('supply_candidates',[]) if any(item in wanted and count>0 and room_for(s,item)>0 for item,count in candidate.get('recorded_items',{}).items())]

def supply_wait(b):return b.get("outcome")=="missing_materials" or b.get("outcome")=="blocked" and b.get("supply_wait",False)

def allowed(s):
    b=s.get('build_job',{})
    if b.get('loading') or s.get('screen') or s.get('manual_movement') or s.get('safety_hold',{}).get('active') or s.get('guard_busy') or s.get('health',0)<14 or any(s.get(k) for k in ('borer_active','planter_active','feeder_active','chopping','navigating')):return {}
    options={'wait':'Wait for existing game/server work; do not interfere.',
             'pause_and_report':'Stop this build and preserve a reproducible report; do not restart automatically.'}
    if not b.get('active'):
        if not supply_wait(b):return {}
        if s.get('supply_protocol',0)>=1 and supply_options(s):options['fetch_supply']='Ask native Kit to visit the nearest authorized recorded depot, verify its live contents, withdraw needed materials into free inventory space, then close it. Recorded stock is only a hint, not current inventory. No block breaking, dropping items, or teleportation.'
        if plank_option(s):options['craft_planks']='Use Kit to convert carried logs into the missing planks through the ordinary inventory recipe. No movement or new resources are required.'
        inventory=stocks(s)
        if b.get('supply_resume_ready',b.get('outcome')=='missing_materials') and any(inventory.get(item,0)>0 for item in b.get('material_needs',{})):options['resume_after_supply']='Usable materials are now present. Resume the SAME unchanged projection that stopped automatically for missing materials.'
        return options
    if b.get('queue_settled'):
        options['rescan']='Refresh the current projection comparison and material deficits without changing blocks.'
        if b.get('auto_move'):options['replan']='Ask Kit to choose a different supported construction position; keep the same projection and materials.'
    return options

def routine_supply_choice(s,options):
    """Native-validated, reversible stock steps do not require an LLM utility decision."""
    if s.get('build_job',{}).get('active') or not supply_wait(s.get('build_job',{})):return None
    for action in ('resume_after_supply','craft_planks','fetch_supply'):
        if action in options:return action
    return None

def compact(s):
    b=s.get('build_job',{});p=s.get('professional_printer',{})
    stock=stocks(s);planks=plank_option(s);recipe=None
    if planks:
        raw=planks.replace('_planks','_log');deficit=max(0,b['material_needs'][planks]-stock.get(planks,0))
        operations=min(stock[raw],(deficit+3)//4,16,room_for(s,planks)//4)
        recipe={'output':planks,'input':raw,'input_on_hand':stock[raw],'input_to_use':operations,
                'output_count':operations*4,'deficit':deficit,'covers_current_deficit':operations*4>=deficit,
                'validated_by':'local inventory and vanilla recipe checks'}
    return {'job':b.get('session'),'placement':b.get('placement_key'),'active':b.get('active'),
            'phase':b.get('phase'),'reason':str(b.get('reason',''))[:240],
            'matched':b.get('matched',0),'total':b.get('total',0),'outcome':b.get('outcome'),
            'deficits':dict(list(b.get('material_deficits',{}).items())[:8]),'blocked_blocks':b.get('blocked_blocks',0),
            'navigation':b.get('navigation',{}),'queue_settled':b.get('queue_settled'),'waiting_for_server':p.get('waiting_for_server',False),
            'health':s.get('health'),'food':s.get('food'),'bridge_version':s.get('bridge_version'),
            'craftable_planks':planks,'recipe_plan':recipe,'stop_was_manual':b.get('outcome')=='manual_stop',
            'material_stock':{item:count for item,count in stocks(s).items() if item in b.get('material_needs',{})},
            'supply_candidates':supply_options(s),'native_supply':s.get('build_supply',{})}
