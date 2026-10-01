"""Produce stripped cherry wood in an explicitly owned temporary work cell.

Target is approved-depot finished total. Normal support placement -> axe use ->
normal mining -> real dropped-item pickup produces each stripped log. Generic
interact has no dedicated per-action server ACK, so receipts say live-loaded
state observation; the final native pickup/inventory delta proves the material.
No user's existing log is stripped, no AirPlace is used, no unknown action is
repeated and cleanup may remove only this journal's confirmed owned block.
"""
import json
import math
from pathlib import Path
import time

from kit_runtime.journal import write_json
from material_cleanup import register, complete
from material_depots import audit, exchange
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from work_access import approach_faces
from .protocol import JobPaused

RAW = 'minecraft:cherry_log'
STRIPPED = 'minecraft:stripped_cherry_log'
OUTPUT = 'minecraft:stripped_cherry_wood'
OUTPUTS = frozenset({OUTPUT})
TARGET_SCOPE = 'approved_depot_total'
MAX_TARGET_COUNT = 100000
RAW_STATE = 'Block{minecraft:cherry_log}[axis=y]'
STRIPPED_STATE = 'Block{minecraft:stripped_cherry_log}[axis=y]'
SUPPORTS = {'minecraft:' + n for n in ('stone', 'cobblestone', 'stone_bricks',
            'diorite', 'andesite', 'granite', 'tuff', 'calcite', 'deepslate', 'obsidian')}
AXES = {'minecraft:' + n + '_axe' for n in ('wooden', 'stone', 'iron', 'golden', 'diamond', 'netherite')}


def _wait(code, detail, **proof):
    return {'phase': 'waiting', 'code': code, 'detail': detail,
            'target_scope': TARGET_SCOPE, **proof}


def worksite(profile):
    site = profile.get('stripped_wood_worksite')
    if not isinstance(site, dict) or site.get('owned') is not True:return None
    cell = site.get('cell')
    if (not isinstance(cell, list) or len(cell) != 3 or any(type(v) is not int for v in cell)
            or not -63 <= cell[1] <= 318 or any(abs(cell[i]) >= 29999984 for i in (0, 2))):return None
    support = [cell[0], cell[1] - 1, cell[2]]
    if site.get('support', support) != support:return None
    expected = site.get('support_state')
    if expected not in {'Block{' + item + '}' for item in SUPPORTS}:return None
    return {'cell': cell, 'support': support, 'support_state': expected}


def choose_axe(state):
    values = [r for r in state.get('inventory', []) if r.get('item') in AXES and r.get('count') == 1
              and type(r.get('slot')) is int and 0 <= r['slot'] < 36
              and type(r.get('durability')) is int and r['durability'] >= 4]
    return max(values, key=lambda r: r['durability'], default=None)


def axe_identity(row):
    return {k: v for k, v in row.items() if k not in ('slot', 'count', 'damage', 'durability')}


def recipe(backend):
    catalog = getattr(backend, 'crafting_catalog', None)
    if catalog is None:return None
    try:choices = catalog.candidates(OUTPUT, {STRIPPED: 4}, 2)
    except ValueError:return None
    return next((r for r in choices if r.get('output') == OUTPUT and r.get('produces') == 3
                 and r.get('width') == 2 and r.get('ingredients') == {STRIPPED: [1,2,3,4]}), None)


def run(c, profile, item, target_count, out, checkpoint):
    if item not in OUTPUTS or type(target_count) is not int or not 1 <= target_count <= MAX_TARGET_COUNT:
        return _wait('unsupported_stripped_wood', 'This adapter produces actual stripped_cherry_wood only')
    backend = (getattr(c, 'stripped_wood_backend', None) or getattr(c, 'wood_backend', None)
               or getattr(c, 'material_backend', None))
    if (backend is None or getattr(backend, 'client', None) is not c or getattr(backend, 'profile', None) != profile
            or getattr(backend, 'request', {}).get('mode') == 'projection'):
        return _wait('wait_source', 'Bind the existing item-mode Backend.client; no controller is created')
    depots = profile.get('depots')
    if (not isinstance(depots, list) or not depots
            or any(not isinstance(p,list) or len(p)!=3 or any(type(v) is not int for v in p) for p in depots)
            or len({tuple(p) for p in depots}) != len(depots)):
        return _wait('wait_source', 'Distinct approved canonical depot inventories are required')
    verified_recipe = recipe(backend)
    if verified_recipe is None:return _wait('wait_recipe', 'Current JAR does not verify4 stripped cherry logs ->3 wood')
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    path = out / 'stripped-wood-pipeline.json'
    spec = {'world_session': c.world, 'item': item, 'target': target_count,
            'target_scope': 'approved_depot_total', 'depots': depots}
    if path.exists():
        job = json.loads(path.read_text())
        if any(job.get(k) != v for k, v in spec.items()):return _wait('wait_receipt', 'Other scope/target journal retained')
        if job.get('pending'):return _wait('wait_receipt', 'Unknown prior mutation retained; no replay', pending=job['pending'])
    else:job = {'schema':1, **spec, 'pending':None, 'expected_depot':None, 'owned_cell':None, 'events':[], 'source_round':0}
    def save():write_json(path, job)
    def state():
        checkpoint(); s = c.status()
        if (s.get('world_session') != c.world or not s.get('connected') or s.get('health',0) < 19
                or s.get('food',0) < 8 or not s.get('guard_armed') or not s.get('guard_pve_only')
                or s.get('manual_movement') or s.get('under_water') or (s.get('safety_hold') or {}).get('active')
                or s.get('dimension') != profile.get('dimension')
                or str(s.get('server','')).lower().removesuffix(':25565') != profile.get('server','').lower().removesuffix(':25565')
                or (s.get('menu') or {}).get('cursor',{}).get('count',0)):
            raise JobPaused('Stripped wood scope, health or cursor changed; work frozen')
        return s
    def stocks():return dict(inventory_counts(state()))
    def begin(kind, **data):job['pending']={'kind':kind, **data};save()
    def known(kind, **data):job['events'].append({'kind':kind, **data});job['pending']=None;save()
    def depot():
        backend.prepare_travel(); backend.stage_near_base(depots)
        proof=audit(c, depots, [OUTPUT])
        if proof.get('complete') is not True or proof.get('world_session') != c.world:raise JobPaused('Depot audit incomplete')
        return proof['counts'][OUTPUT], proof
    def scan(site):
        s=state(); cell=site['cell']; support=site['support']
        reply=c.request('scan', min=support, max=[cell[0],cell[1]+2,cell[2]], details=True)
        if (reply.get('phase') not in (None,'done') or reply.get('world_session') != c.world
                or not isinstance(reply.get('blocks'),list)):raise JobPaused('Work column not loaded on current server')
        rows={}
        for row in reply['blocks']:
            p=row.get('pos')
            if (not isinstance(p,list) or len(p)!=3 or any(type(v) is not int for v in p)
                    or p[0]!=cell[0] or p[2]!=cell[2]
                    or not support[1] <= p[1] <= cell[1]+2 or tuple(p) in rows):raise JobPaused('Invalid worksite scan')
            rows[tuple(p)]=row
        anchor=rows.get(tuple(support))
        if (not anchor or anchor.get('state')!=site['support_state'] or anchor.get('solid') is not True
                or anchor.get('fluid') is not False or anchor.get('block_entity') is not False
                or any((cell[0],y,cell[2]) in rows for y in (cell[1]+1,cell[1]+2))):
            raise JobPaused('Owned work support/headroom changed; no interaction')
        target=rows.get(tuple(cell))
        if target and (target.get('fluid') is not False or target.get('block_entity') is not False):
            raise JobPaused('Work cell is wet or a block entity')
        return target.get('state') if target else 'AIR', s
    def observed(site, expected, predicate):
        start=time.monotonic(); first=None
        while time.monotonic()-start < 4:
            current, s=scan(site)
            if type(s.get('time')) not in (int,float) or not math.isfinite(s['time']):
                raise JobPaused('A fresh native observation timestamp is required')
            if current==expected and predicate(inventory_counts(s)):
                if first is not None and s.get('time',0)-first >= 400:return s
                if first is None:first=s.get('time',0)
            else:first=None
            time.sleep(.1)
        raise JobPaused('Expected work state/inventory did not settle; no mutation replay')
    def select(item, slot=None):
        c.checked('select_item', item=item, **({'slot':slot} if slot is not None else {}))
        s=state()
        if s.get('hand',{}).get('item') != item:raise JobPaused('Selected hand metadata changed')
        return s
    def axe_ready(axe):
        s=select(axe['item'], axe['slot'])
        current=next((r for r in s['inventory'] if r.get('slot')==s.get('selected_slot')), None)
        if not current or axe_identity(current)!=axe_identity(axe) or current.get('durability',0)<2:
            raise JobPaused('Actual axe metadata/durability changed')
        return current
    def retrieve_owned(site, expected, returned, baseline):
        owner=job.get('owned_cell')
        if (not owner or not owner.get('confirmed') or owner.get('world_session') != c.world
                or owner.get('cell') != site['cell'] or owner.get('state') != expected):
            raise JobPaused('Only the exactly confirmed owned block may be mined')
        current,_=scan(site)
        if current!=expected:raise JobPaused('Owned work block changed; do not mine another block')
        axe=choose_axe(state())
        if axe is None:raise JobPaused('Durable normal axe required for owned retrieval')
        face=approach_faces(c,site['cell'],expected,('up','north','south','east','west'),seconds=30,stand_distance=1.8)
        axe_ready(axe)
        prior=state(); old_ids={e.get('uuid') for e in prior.get('entities',[]) if e.get('type')=='minecraft:item'}
        begin('mine_owned', cell=site['cell'], expected=expected, returned=returned, baseline=baseline)
        reply=c.request('mine_block',pos=site['cell'],face=face,expected_state=expected,seconds=30)
        if reply.get('phase')!='done':raise JobPaused('Owned mining outcome unknown; no second mine')
        start=time.monotonic(); drop=None
        while time.monotonic()-start < 4:
            s=state(); held=inventory_counts(s).get(returned,0)
            if held==baseline+1:break
            if held!=baseline:raise JobPaused('Retrieval inventory changed by an unexpected quantity')
            drop=next((e for e in s.get('entities',[]) if e.get('type')=='minecraft:item'
                 and isinstance(e.get('uuid'),str) and e['uuid'] and e.get('uuid') not in old_ids
                 and e.get('stack',{}).get('item')==returned
                 and e['stack'].get('count')==1 and isinstance(e.get('pos'),list) and len(e['pos'])==3
                 and all(type(v) in (int,float) and math.isfinite(v) for v in e['pos'])
                 and math.dist(e['pos'],[v+.5 for v in site['cell']])<=3),None)
            if drop:
                begin('pickup_owned',cell=site['cell'],uuid=drop['uuid'],baseline=baseline,returned=returned)
                picked=c.request('collect_item',expected_uuid=drop['uuid'],expected_item=returned,expected_count=1,seconds=30)
                if picked.get('phase')!='done':raise JobPaused('Native single-drop pickup unknown; no replay')
                break
            time.sleep(.1)
        observed(site,'AIR',lambda stock:stock.get(returned,0)==baseline+1)
        latest=state()
        current_axe=next((r for r in latest['inventory'] if r.get('slot')==latest.get('selected_slot')),None)
        if (not current_axe or axe_identity(current_axe)!=axe_identity(axe)
                or current_axe.get('durability',0)<1):
            raise JobPaused('Actual axe metadata changed during owned retrieval')
        job['owned_cell']=None
        known('owned_retrieved', returned=returned, gained=1, drop_uuid=drop.get('uuid') if drop else None,
              proof_scope='native_drop_pickup_or_server_inventory_delta_plus_live_loaded_air')
    def cleanup_owned():
        if job.get('pending'):raise JobPaused('Uncertain owned work operation retained; cleanup must not replay')
        owner=job.get('owned_cell')
        if not owner:return
        site=worksite(profile)
        if site is None:raise JobPaused('Owned cleanup worksite no longer configured')
        expected=owner['state']; returned=RAW if expected==RAW_STATE else STRIPPED if expected==STRIPPED_STATE else None
        if returned is None:raise JobPaused('Cleanup state not confirmed as our owned cherry block')
        retrieve_owned(site,expected,returned,stocks().get(returned,0))

    state(); save()
    if job.get('owned_cell'):
        cleanup_key='stripped-wood:'+str(path.resolve())
        register(c,cleanup_key,cleanup_owned)
        cleanup_owned()  # Only a prior confirmed owned state, never an uncertain pending action.
        complete(c,cleanup_key)
        return _wait('owned_cell_restored','Confirmed temporary work block was retrieved; no new strip started')
    current, proof=depot()
    if job['expected_depot'] is not None and current!=job['expected_depot']:
        return _wait('wait_depot','Finished stock changed outside journal',expected=job['expected_depot'],observed=current)
    job['expected_depot']=current;save()
    if current>=target_count:return {'phase':'done','item':OUTPUT,'target_scope':'approved_depot_total','depot_count':current,'audit':proof}
    held=stocks(); finished=held.get(OUTPUT,0)
    if finished:
        amount=min(finished,target_count-current);begin('deposit',before=finished,depot=current,amount=amount)
        result=exchange(c,depots,deposit={OUTPUT:finished-amount})
        after=stocks().get(OUTPUT,0); new, proof=depot()
        if not 0<=finished-after<=amount or new-current!=finished-after:
            return _wait('wait_receipt','Deposit conservation unknown; pending retained')
        job['expected_depot']=new;known('deposited',moved=finished-after,audit=proof,exchange=result)
        return {'phase':'done' if new>=target_count else 'waiting','code':'complete' if new>=target_count else 'batch_delivered',
                'target_scope':'approved_depot_total','depot_count':new,'carried_surplus':after}
    if held.get(STRIPPED,0)>=4:
        rounds=min(4,held[STRIPPED]//4,math.ceil((target_count-current)/3))
        produced=rounds*3
        if room_for_item(state(),OUTPUT)<produced:return _wait('wait_capacity','Make space without discarding items')
        target=held.get(OUTPUT,0)+produced;begin('craft',target=target,inputs=rounds*4,recipe=verified_recipe['recipe_id'])
        result=backend.craft({OUTPUT:target});after=stocks()
        if (result.get('phase')!='done' or after.get(OUTPUT,0)-held.get(OUTPUT,0)!=produced
                or held.get(STRIPPED,0)-after.get(STRIPPED,0)!=rounds*4):
            return _wait('wait_receipt','Actual4-to3 recipe result unknown; pending retained')
        known('crafted',produced=produced,inputs=rounds*4,recipe=verified_recipe['recipe_id'],result=result)
        return _wait('batch_crafted','Actual stripped wood is carried; next call deposits it',produced=produced)
    site=worksite(profile)
    if site is None:return _wait('wait_worksite','Configure an explicitly owned AIR work cell over a dry noninteractive support')
    if room_for_item(state(),STRIPPED)<1:return _wait('wait_capacity','Reserve a slot for the actual stripped log drop')
    backend.prepare_travel();backend.stage_near_base([site['cell']])
    cell_state,_=scan(site)
    if cell_state!='AIR':return _wait('wait_worksite','Work cell is not AIR; existing user blocks are never stripped or removed')
    axe=choose_axe(state())
    if axe is None:return _wait('wait_tool','A real normal axe with at least4 durability is required')
    if not held.get(RAW,0):
        begin('fetch_raw',target=4)
        fetched=backend.fetch({RAW:4});held=stocks()
        if (not isinstance(fetched,dict) or fetched.get('phase') not in ('done','waiting')
                or fetched.get('phase')=='waiting' and not isinstance(fetched.get('missing'),dict)):
            return _wait('wait_receipt','Raw source transfer unconfirmed')
        known('raw_fetched',receipt=fetched)
        if not held.get(RAW,0):
            from .wood_pipeline import run as wood_run
            existing=getattr(c,'wood_backend',None); changed=existing is None
            if changed:c.wood_backend=backend
            begin('produce_raw')
            source_dir=out/('cherry-source-%04d'%job.get('source_round',0))
            try:supplied=wood_run(c,profile,RAW,4,source_dir,checkpoint)
            finally:
                if changed and getattr(c,'wood_backend',None) is backend:delattr(c,'wood_backend')
            if supplied.get('code')=='wait_receipt':return _wait('wait_receipt','Cherry supplier has uncertain work; retain it',source=supplied)
            if supplied.get('phase')=='done' or supplied.get('code')=='batch_delivered':
                job['source_round']=job.get('source_round',0)+1  # A new source job only after known stock delivery.
            known('raw_supplier',receipt=supplied)
            return _wait('wait_source','Cherry logs not yet carried; next call fetches only verified actual supply',source=supplied)
    # One and only one supported raw log is placed, stripped and retrieved.
    held=stocks();raw_before=held.get(RAW,0); stripped_before=held.get(STRIPPED,0)
    face=approach_faces(c,site['support'],site['support_state'],('up',),seconds=30,stand_distance=1.8)
    select(RAW)
    if scan(site)[0]!='AIR':return _wait('wait_worksite','Work cell changed before placement')
    begin('place_raw',cell=site['cell'],raw_before=raw_before,stripped_before=stripped_before)
    reply=c.request('interact',pos=site['support'],face=face,expected_state=site['support_state'],expected_hand=RAW)
    if reply.get('phase')!='done':return _wait('wait_receipt','Supported placement unknown; no second placement')
    observed(site,RAW_STATE,lambda stock:stock.get(RAW,0)==raw_before-1 and stock.get(STRIPPED,0)==stripped_before)
    job['owned_cell']={'confirmed':True,'world_session':c.world,'cell':site['cell'],'state':RAW_STATE}
    known('placed_owned',raw_consumed=1,observed_state=RAW_STATE,proof_scope='live_loaded_state_and_exact_raw_inventory_delta')
    cleanup_key='stripped-wood:'+str(path.resolve());register(c,cleanup_key,cleanup_owned)
    axe=choose_axe(state())
    if axe is None:return _wait('wait_tool','Axe changed after owned placement; safe owned cleanup remains registered')
    face=approach_faces(c,site['cell'],RAW_STATE,('up','north','south','east','west'),seconds=30,stand_distance=1.8)
    axe_ready(axe)
    if scan(site)[0]!=RAW_STATE:raise JobPaused('Owned log changed before normal axe use')
    begin('strip_owned',cell=site['cell'],raw_state=RAW_STATE,axe=axe)
    stripped=c.request('interact',pos=site['cell'],face=face,expected_state=RAW_STATE,expected_hand=axe['item'])
    if stripped.get('phase')!='done':return _wait('wait_receipt','Axe use unknown; no retry or cleanup mutation')
    observed(site,STRIPPED_STATE,lambda stock:stock.get(RAW,0)==raw_before-1 and stock.get(STRIPPED,0)==stripped_before)
    latest=state()
    current_axe=next((r for r in latest['inventory'] if r.get('slot')==latest.get('selected_slot')),None)
    if not current_axe or axe_identity(current_axe)!=axe_identity(axe):raise JobPaused('Actual axe metadata changed while stripping')
    job['owned_cell']['state']=STRIPPED_STATE
    known('stripped_owned',observed_state=STRIPPED_STATE,axe=current_axe,
          proof_scope='normal_axe_interaction_then_live_loaded_state; not a dedicated packet ACK')
    retrieve_owned(site,STRIPPED_STATE,STRIPPED,stripped_before)
    begin('verify_conversion',raw_before=raw_before,stripped_before=stripped_before)
    if stocks().get(RAW,0)!=raw_before-1:return _wait('wait_receipt','Raw-log net consumption differs from one owned conversion')
    known('conversion_verified',raw_consumed=1,stripped_log_gained=1)
    complete(c,cleanup_key)
    return _wait('stripped_log_produced','One actual stripped cherry log collected; wood crafting remains separate',
                 raw_consumed=1,stripped_log_gained=1,work_cell_restored=True,
                 build_limit='stripped_cherry_wood has axis properties; this adapter does not claim plain Scaffold placement support')
