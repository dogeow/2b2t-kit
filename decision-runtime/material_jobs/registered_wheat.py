"""Borrow completed Kit wheat fields and the existing harvest/reseed primitive."""
import hashlib
import json
from pathlib import Path

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from potato_farm import FarmWait, _properties, plan
from potato_harvest import _registered_wheat, run as harvest
from potato_loot_flight import make_pickup
from .protocol import server_key


def registered_fields(c):
    """Read original planting registrations; never create fields or credit stock."""
    for path in sorted((Path(c.root)/'farms').glob('*/registry.json'))[:32]:
        try:
            if path.stat().st_size>1_000_000:continue
            saved=json.loads(path.read_text());scope=saved['scope'];layout=scope['layout']
            if (scope['server']!=server_key(c.server) or scope['dimension']!='minecraft:overworld'
                    or layout.get('crop')!='wheat'):continue
            request={'authorized':True,'center':layout['center'],'radius':layout['radius'],
                     'crop':'wheat','bonemeal':False,'reverify_registered_field':True}
            if plan(request)!=layout:continue
            key=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]
            if path.parent.name!=key:continue
            yield request,path
        except (OSError,ValueError,KeyError,TypeError,AttributeError):continue


def run(backend,target,out,checkpoint):
    if type(target) is not int or not 1<=target<=64:raise ValueError('Wheat target must be carried total 1..64')
    c=backend.ensure_client();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    before=inventory_counts(c.status())['minecraft:wheat']
    if before>=target:return {'phase':'done','before':before,'after':before}
    wait=lambda code,detail,**extra:{'phase':'waiting','code':code,'detail':detail,
                                  'requirements':{'minecraft:wheat':target},**extra}
    fields=list(registered_fields(c))
    if not fields:return wait('WAIT_REGISTERED_FARM','No original Kit wheat planting registration')
    try:
        for number,(request,registry) in enumerate(fields):
            checkpoint();layout=plan(request);home=out/('field-%02d'%number);home.mkdir(exist_ok=True)
            # This existing primitive proves original complete planting, no old
            # pending harvest, and two current complete crop/farmland frames.
            _registered_wheat(c,{**request,'cells':layout['cells']},home/'preflight.json',bind_active=False)
            scan=c.checked('scan',min=layout['scan_min'],max=layout['scan_max'],details=True)
            expected=1
            for low,high in zip(layout['scan_min'],layout['scan_max']):expected*=high-low+1
            if (scan.get('world_session')!=c.world or scan.get('phase')!='done'
                    or scan.get('scan_cells_read')!=expected or scan.get('scan_total_cells')!=expected):
                return wait('WAIT_SCAN','Registered wheat maturity scan incomplete')
            rows={tuple(row['pos']):row for row in scan['blocks']}
            mature=[p for p in layout['cells'] if _properties(rows.get((p[0],p[1]+1,p[2]),{}),'wheat','age',7)==7]
            write_json(home/'source-observation.json',{'world_session':c.world,'registry':str(registry),
                       'mature_cells':mature,'inventory_credit':0})
            if not mature:continue
            if inventory_counts(c.status())['minecraft:wheat_seeds']<5:
                fetched=backend.fetch({'minecraft:wheat_seeds':5})
                if fetched.get('phase') not in ('done','waiting'):
                    return wait('WAIT_RECONCILE','Registered field seed supply uncertain',receipt=fetched)
                if inventory_counts(c.status())['minecraft:wheat_seeds']<5:
                    return wait('WAIT_SEED','Registered wheat harvest keeps the existing four-seed reserve',
                                requirements={'minecraft:wheat_seeds':5})
            backend.prepare_travel()
            from .navigation import lift_for_travel,settled_state
            from .acquisition import _travel
            lift_for_travel(c)
            center=layout['center'];trace=[]
            _travel(c,[center[0]+.5,max(c.status()['pos'][1],center[1]+24),center[2]+.5],
                    checkpoint,trace,keep_cruise=True)
            write_json(home/'travel.json',trace)
            hover=[center[0]+.5,center[1]+1.6,center[2]+.5]
            c.checked('navigate',target=hover,arrival=.15,air_only=True,seconds=45)
            settled_state(c,hover,.6)
            cells=mature[:min(4,target-before)]
            result=harvest(c,{**request,'cells':cells},home,checkpoint,max_cells=4,bonemeal_budget=0,
                           pickup=make_pickup(center,radius=layout['radius'],checkpoint=checkpoint,crop='wheat'))
            write_json(home/'result.json',result)
            # A remaining harvested cell/drop must stay with its original
            # reconciler; a generic source wait must not abandon replanting.
            books=list(home.glob('wheat-harvest-*.json'))
            pending=any((b.get('pending') or b.get('cleanup_pending')) for b in
                        (json.loads(p.read_text()) for p in books))
            if result.get('phase')!='done' or pending or not books:
                return wait('WAIT_RECONCILE','Original registered wheat harvest needs reconciliation',receipt=result)
            after=inventory_counts(c.status())['minecraft:wheat']
            if after<=before or not result.get('harvested_replanted'):
                return wait('WAIT_RECONCILE','Registered wheat receipt lacks a fresh carried gain and restored cell')
            return {'phase':'done' if after>=target else 'waiting','code':'SOURCE_BATCH',
                    'before':before,'after':after,'gained':after-before,'journal':str(home),
                    'registered_field_replanted':True}
        return wait('WAIT_GROWTH','Existing registered wheat is not currently mature')
    except FarmWait as error:
        return wait(error.code,str(error),**({'active_journal':error.active_journal}if hasattr(error,'active_journal')else{}))
