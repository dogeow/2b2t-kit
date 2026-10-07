"""Same-JVM source handoff of an already admitted material plan.

The new worker reads current inventory and construction itself. Historical
unknown actions remain unknown, and only a new native Start/Resume owns work.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import uuid

from singleplayer_trial_bridge import Paused, complete_scan, native_inventory_click_proof, native_inventory_probe_proof
from trial_inventory_audit import record, file_hash, exact_side, empty_menu, quantities
from survival_world import World, block_id

KIND = 'same_session_source_material_handoff'
ID = re.compile(r'handoff-[a-f0-9]{32}\Z')
WORK_KEYS = ('owned', 'stations', 'small_shelter', 'excluded', 'camp')


def pid_alive(pid):
    try: os.kill(pid, 0)
    except ProcessLookupError: return False
    except PermissionError: return True
    return True


def point(value):
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(type(n) is int and abs(n) <= 30_000_000 for n in value))


def frozen_unchanged(frozen):
    if not isinstance(frozen, dict) or not frozen:
        raise Paused('Source handoff has no frozen admitted evidence')
    for filename, digest in frozen.items():
        if not isinstance(filename, str) or not re.fullmatch(r'[a-f0-9]{64}', str(digest)) or file_hash(filename) != digest:
            raise Paused('Source handoff evidence changed; preserve both plans')


def _scope(state, worker):
    return all(state.get(k) == v for k, v in {
        'world_id': worker.registry['world_id'], 'world_session': worker.bridge.session,
        'dimension': worker.bridge.state['dimension'], 'game_version': '26.1.2',
        'server': 'singleplayer', 'connected': True}.items())


def _released(state):
    keys = state.get('movement_keys', {})
    return (state.get('phase') != 'running' and not state.get('screen')
            and state.get('manual_movement') is False
            and all(state.get(k) is False for k in ('chopping', 'navigating', 'borer_active', 'printing'))
            and {'forward', 'back', 'jump', 'sneak'} <= keys.keys()
            and all(v is False for v in keys.values()) and empty_menu(state.get('menu')))


def _sdk_commits(worker, manifest, frozen):
    ids = manifest.get('sdk_inventory_confirmed_ids')
    if (not isinstance(ids, list) or len(ids) > 4096 or len(set(ids)) != len(ids)
            or any(not isinstance(rid, str) or not re.fullmatch(r'trial-[A-Za-z0-9_-]{1,74}', rid) for rid in ids)):
        raise Paused('Source material handoff lacks exact SDK commits')
    root = worker.automation / 'trial-sdk-inventory'
    for rid in ids:
        original = root / 'pending' / (rid + '.json')
        settled = root / 'receipts' / (rid + '.json')
        if any(frozen.get(str(path)) != file_hash(path) for path in (original, settled)):
            raise Paused('Source SDK commit is not frozen with its exact original intent')
        intent = record({'path': str(original), 'sha256': frozen[str(original)]}, 512_000)
        receipt = record({'path': str(settled), 'sha256': frozen[str(settled)]}, 1_000_000)
        envelope = intent.get('envelope', {})
        if (intent.get('request_id') != rid or envelope.get('id') != rid
                or envelope.get('run_id') != manifest['source_run_id']
                or envelope.get('world_session') != manifest['world_session']
                or envelope.get('world_id') != manifest['world_id']
                or envelope.get('trial_id') != manifest['trial_id']
                or receipt.get('request_id') != rid or receipt.get('intent_sha256') != frozen[str(original)]
                or receipt.get('receipt_class') != 'sdk_inventory_click_committed'
                or receipt.get('sdk_predicate_confirmed') is not True or receipt.get('replayed') is not False):
            raise Paused('Source SDK history contains an unconfirmed or foreign click')
        proof = native_inventory_click_proof(receipt.get('native_result'), envelope, intent.get('before', {}))
        stamps = receipt.get('witness_times')
        if (proof['classification'] != 'confirmed' or not isinstance(stamps, list) or len(stamps) != 2
                or any(type(t) is not int for t in stamps)
                or not receipt['native_result']['time'] < stamps[0] < stamps[1]):
            raise Paused('Source SDK history lacks its two real post-click predicates')


def validate_handoff(worker, state, *, pointer=None, process_alive=pid_alive):
    """Verify already approved authorization and normal source retirement, without replay."""
    pointer = worker.output / 'source-material-handoff.json' if pointer is None else Path(pointer)
    ref = json.loads(pointer.read_text())
    manifest_path = Path(ref.get('path', ''))
    folder = worker.output / 'source-material-handoffs'
    if (pointer.is_symlink() or not manifest_path.is_absolute() or manifest_path.parent != folder
            or not ID.fullmatch(manifest_path.stem)):
        raise Paused('Source handoff must name one immutable local manifest')
    manifest = record(ref, 8_000_000)
    if (manifest.get('schema') != 1 or manifest.get('kind') != KIND or manifest.get('id') != manifest_path.stem
            or worker.native_start_run != worker.run_id or worker.command != 'start'
            or not _scope(state, worker)
            or any(manifest.get(k) != state.get(k) for k in ('world_id', 'world_session', 'dimension', 'game_version', 'kit_version'))
            or manifest.get('trial_id') != worker.registry['trial_id']
            or not isinstance(manifest.get('source_run_id'), str) or not manifest['source_run_id']
            or manifest['source_run_id'] == worker.run_id
            or manifest.get('source_worker_exited') is not True
            or type(manifest.get('source_worker_pid')) is not int or manifest['source_worker_pid'] <= 1
            or manifest['source_worker_pid'] == os.getpid() or process_alive(manifest['source_worker_pid'])
            or type(manifest.get('source_parent_pid')) is not int or manifest['source_parent_pid'] != worker.parent_pid
            or not re.fullmatch(r'[a-f0-9]{64}', str(manifest.get('bundle_sha256', '')))
            or worker.bridge.halted or worker.bridge.pending_mutations or worker.bridge.active is not None):
        raise Paused('Source material handoff differs from this new native Start in the same Minecraft process')
    frozen = manifest.get('frozen');frozen_unchanged(frozen)
    previous_ref=manifest.get('original_manifest_ref',manifest.get('supersedes_ref'))
    if previous_ref is not None:
        previous=record(previous_ref,8_000_000);previous_path=Path(previous_ref['path'])
        if (previous_path.parent!=folder or not ID.fullmatch(previous_path.stem)
                or previous.get('id')!=previous_path.stem or previous.get('id')==manifest['id']
                or frozen.get(str(previous_path))!=previous_ref['sha256']
                or (worker.output/'source-material-handoff-claims'/(previous['id']+'.json')).exists()
                or any(manifest.get(key)!=previous.get(key) for key in ('schema','kind','world_id','trial_id','world_session','dimension',
                    'game_version','kit_version','source_run_id','source_worker_pid','source_parent_pid','source_worker_exited',
                    'lifecycle_kind','baseline','checkpoint','sdk_inventory_confirmed_ids','historical_pending','protected_player_work',
                    'source_stopped_native','source_worker_status'))
                or not isinstance(previous.get('frozen'),dict)
                or any(frozen.get(path)!=digest for path,digest in previous['frozen'].items())):
            raise Paused('Source handoff supersedes a claimed, changed or different original grant')
    baseline = record(manifest.get('baseline'));checkpoint = record(manifest.get('checkpoint'))
    for reference in (manifest['baseline'], manifest['checkpoint']):
        if frozen.get(reference['path']) != reference['sha256']:
            raise Paused('Source admitted plan and checkpoint are not frozen')
    old = manifest.get('historical_pending')
    inventory_ids = {row.get('id') for row in old or [] if isinstance(row, dict) and row.get('op') == 'slot_click'}
    if (not isinstance(old, list) or old != worker.legacy_pending or baseline.get('legacy_pending') != old
            or baseline.get('schema') != 1 or baseline.get('source') != 'fresh_kit_physical_baseline'
            or baseline.get('run_id') != manifest['source_run_id']
            or any(baseline.get(k) != manifest.get(k) for k in ('world_id', 'trial_id', 'world_session', 'dimension'))
            or baseline.get('historical_effects_unresolved') is not True
            or baseline.get('old_action_completed') is not False or baseline.get('old_action_replayed') is not False
            or set(baseline.get('inventory_review_verified_ids', [])) != inventory_ids
            or set(baseline.get('forbidden_request_ids', [])) != {row.get('id') for row in old}
            or checkpoint.get('schema') != 1 or checkpoint.get('source_run_id') != manifest['source_run_id']
            or checkpoint.get('material_baseline_id') != baseline.get('newbaseline_id')
            or checkpoint.get('unresolved_native') != []
            or checkpoint.get('historical_unresolved_native') != old
            or any(checkpoint.get(k) != manifest.get(k) for k in ('world_id', 'trial_id', 'world_session', 'game_version'))
            or manifest.get('protected_player_work') != {k: checkpoint.get(k) for k in WORK_KEYS}):
        raise Paused('Source handoff lost approved authority, unknown history or current player work')
    review = baseline.get('review', {})
    if (not isinstance(review, dict) or not isinstance(review.get('request'), dict)
            or review.get('report', {}).get('decision') != 'fresh_replan_allowed'
            or review.get('report', {}).get('historical_effects_unresolved') is not True
            or any(frozen.get(path) != digest for path, digest in review['request'].get('frozen_legacy', {}).items())):
        raise Paused('Source handoff does not retain the prior admitted operator review')
    witness = manifest.get('operator_current_native', manifest.get('after_cancel_native'))
    if (not isinstance(witness, dict) or not _scope(witness, worker) or not _released(witness)
            or witness.get('player_uuid') != state.get('player_uuid')
            or witness.get('trial_identity', {}).get('process_alive') is not False):
        raise Paused('Source handoff has no released current-stock witness')
    mode = manifest.get('lifecycle_kind', 'native_pause_cancel')
    if mode == 'native_pause_cancel':
        for name, command in (('native_pause_reply', 'pause'), ('native_cancel_reply', 'cancel')):
            reply = manifest.get(name, {})
            identity = reply.get('trial_identity', {})
            if (reply.get('protocol') != 1 or reply.get('phase') != 'done'
                    or identity.get('trial_id') != manifest['trial_id'] or identity.get('run_id') != manifest['source_run_id']
                    or identity.get('world_id') != manifest['world_id']):
                raise Paused('Source handoff lacks this worker\'s exact native lifecycle reply')
            path = worker.root / ('api-intent-' + str(reply.get('id')) + '.json')
            if frozen.get(str(path)) != file_hash(path):
                raise Paused('Source lifecycle intent is not frozen')
            request = record({'path': str(path), 'sha256': frozen[str(path)]}, 131072)
            if request.get('command') != command or request.get('world_session') != manifest['world_session']:
                raise Paused('Source lifecycle intent belongs to another command or connection')
    elif mode == 'manual_stopped_same_session':
        stopped = manifest.get('source_stopped_native', {})
        worker_status = record(manifest.get('source_worker_status'), 262_144)
        if (not _scope(stopped, worker) or stopped.get('trial_identity', {}).get('process_alive') is not False
                or stopped.get('trial_identity', {}).get('detail') != '手动移动接管'
                or worker_status.get('phase') not in ('stopped', 'cancelled')
                or worker_status.get('run_id') != manifest['source_run_id']
                or worker_status.get('pid') != manifest['source_worker_pid']
                or worker_status.get('material_baseline_id') != baseline['newbaseline_id']
                or worker_status.get('material_baseline_session') != manifest['world_session']
                or frozen.get(manifest['source_worker_status']['path']) != manifest['source_worker_status']['sha256']):
            raise Paused('Manual source retirement does not preserve the same admitted worker')
    else: raise Paused('Unsupported source handoff lifecycle')
    quantities(witness.get('inventory'));_sdk_commits(worker, manifest, frozen)
    return {'manifest': manifest, 'reference': ref, 'baseline': baseline, 'checkpoint': checkpoint,
            'frozen': frozen, 'witness': witness}


def scene_bounds(checkpoint, position):
    """Read all existing owned/station/house cells; distant exclusions stay protective metadata."""
    cells = [tuple(math.floor(n) for n in position)]
    owned = checkpoint.get('owned', {});stations = checkpoint.get('stations', {})
    if not isinstance(owned, dict) or len(owned) > 4096 or not isinstance(stations, dict):
        raise Paused('Source checkpoint has malformed protected work')
    for key, item in owned.items():
        try: p = [int(n) for n in key.split(',')]
        except (ValueError, AttributeError): raise Paused('Source owned cell is malformed') from None
        if not point(p) or not isinstance(item, str): raise Paused('Source owned cell is malformed')
        cells.append(tuple(p))
    for name, p in stations.items():
        if name not in {'crafting_table', 'furnace'} or not point(p): raise Paused('Source station is malformed')
        cells.append(tuple(p))
    small = checkpoint.get('small_shelter')
    if small is not None:
        from trial_safety_preparation import _layout
        if not isinstance(small, dict) or not point(small.get('inside')): raise Paused('Source partial house is malformed')
        plan = _layout(small['inside'])
        if any(small.get(k) != v for k, v in plan.items()): raise Paused('Source partial house geometry changed')
        cells.extend(tuple(p) for key in ('layout', 'floor') for p in plan[key]);cells.extend([tuple(plan['inside']),tuple(plan['door'])])
    low = [min(p[i] for p in cells)-1 for i in range(3)]
    high = [max(p[i] for p in cells)+2 for i in range(3)]
    low[1] = max(-64,low[1]);high[1] = min(319,high[1])
    if math.prod(b-a+1 for a,b in zip(low,high)) > 32768:
        raise Paused('Source player work exceeds one bounded handoff scan; nothing discarded')
    return {'min': low, 'max': high, 'details': True}


def verify_scene(checkpoint, terrain, bounds, revision, world_id, dimension, *, manual_reconcile=False, position=None):
    if not complete_scan(terrain,bounds,revision): raise Paused('Source handoff scene scan is incomplete')
    seen=set()
    for row in terrain['blocks']:
        p=row.get('pos') if isinstance(row,dict) else None
        if (not point(p) or tuple(p) in seen or not all(bounds['min'][i]<=p[i]<=bounds['max'][i] for i in range(3))
                or not isinstance(row.get('state'),str)
                or any(type(row.get(key)) is not bool for key in ('solid','fluid','passable','block_entity'))):
            raise Paused('Source handoff scene contains malformed or duplicate cells')
        seen.add(tuple(p))
    world = World(terrain['blocks'],bounds['min'],bounds['max'])
    absent=[];existing_variants=[]
    small=checkpoint.get('small_shelter')
    partial_cells={tuple(p) for p in small.get('layout',[])} if isinstance(small,dict) and small.get('verified') is False else set()
    for key, item in checkpoint['owned'].items():
        p = tuple(int(n) for n in key.split(','))
        if world.name(p) != item.removeprefix('minecraft:'):
            from trial_safety_preparation import SITE_PLANTS
            actual=world.name(p);observed=world.row(p)
            if (item.removeprefix('minecraft:')=='dirt' and p in partial_cells and world.known(p)
                    and actual=='grass_block' and observed.get('solid') is True
                    and observed.get('fluid') is False and observed.get('block_entity') is False):
                # Dirt and ordinary grass are both existing full earth walls.
                # Keep this occupied cell protected without attributing its origin.
                existing_variants.append({'key':key,'pos':list(p),'expected':item,'actual':actual,
                    'observed_state':observed['state'],'attribution':'unresolved','old_placement_ack_confirmed':False})
                continue
            replaceable=(actual=='air' or actual in SITE_PLANTS and observed.get('replaceable') is True and observed.get('passable') is True)
            if (not manual_reconcile or item.removeprefix('minecraft:')!='dirt' or p not in partial_cells
                    or not world.known(p) or not replaceable
                    or observed.get('fluid',False) is not False or observed.get('block_entity',False) is not False):
                raise Paused('Previously placed owned block changed at '+key+'; preserve the partial plan')
            absent.append({'key':key,'pos':list(p),'expected':item,'actual':actual,
                'observed_state':observed.get('state','Block{minecraft:air}'),
                'observation_scope':'fresh_complete_loaded_scene','attribution':'unresolved',
                'historical_effects_unresolved':True,'old_placement_ack_confirmed':False})
    station_changes=[]
    for name,p in checkpoint['stations'].items():
        old=tuple(p)
        if world.name(old) != name:
            from trial_safety_preparation import SITE_PLANTS
            actual=world.name(old);observed=world.row(old)
            replaceable=(actual=='air' or actual in SITE_PLANTS and observed.get('replaceable') is True and observed.get('passable') is True)
            if (not manual_reconcile or not world.known(old) or not replaceable
                    or observed.get('fluid',False) is not False or observed.get('block_entity',False) is not False):
                raise Paused('Current station changed; preserve its recorded coordinate')
            origin=position if position is not None else p
            candidates=[cell for cell,record in world.blocks.items()
                if world.name(cell)==name and record.get('solid') is True
                and record.get('fluid') is False and record.get('block_entity') is False]
            current=min(candidates,key=lambda cell:(math.dist(origin,[cell[0]+.5,cell[1],cell[2]+.5]),cell),default=None)
            station_changes.append({'name':name,'previous':list(p),'actual_previous':actual,
                'previous_state':observed.get('state','Block{minecraft:air}'),
                'current':list(current) if current is not None else None,
                'current_state':world.row(current).get('state') if current is not None else None,
                'observation_scope':'fresh_complete_loaded_scene_positive_station',
                'attribution':'unresolved','old_placement_ack_confirmed':False})
    small = checkpoint.get('small_shelter')
    if small:
        from trial_safety_preparation import _house_verified, _layout
        if small.get('world_id') != world_id or small.get('dimension') != dimension:
            raise Paused('Source partial house belongs to another save')
        reconciled_plants={tuple(row['pos']) for row in absent if row['actual']!='air'}
        if (any(not world.full(tuple(p)) for p in small['floor'])
                or any(world.name(tuple(p)) not in {'air','dirt','grass_block'} and tuple(p) not in reconciled_plants for p in small['layout'])):
            raise Paused('Partial house support or remaining layout changed; no rebuilding authorized')
        if small.get('verified') is True and not _house_verified(world,_layout(small['inside']),small.get('door_item','')):
            raise Paused('Formerly complete house is no longer verified')
    world.reconciled_absent_owned=absent
    world.observed_owned_variants=existing_variants
    world.reconciled_stations=station_changes
    return world


def observe_handoff(worker, checked):
    """Only fresh bounded reads; a new plan never borrows old stock or placement completion."""
    manifest=checked['manifest'];checkpoint=checked['checkpoint'];before=worker.bridge.read()
    bounds=scene_bounds(checkpoint,before['pos']);terrain=worker.bridge.request('scan',**bounds)
    after_scan=worker.bridge.read()
    world=verify_scene(checkpoint,terrain,bounds,after_scan['control_revision'],after_scan['world_id'],after_scan['dimension'],
        manual_reconcile=manifest.get('lifecycle_kind')=='manual_stopped_same_session',position=after_scan['pos'])
    probe_result=worker.bridge.request('inventory_probe');probe=worker.bridge.last_inventory_probe
    if not isinstance(probe,dict): raise Paused('Source handoff needs a new worker-owned server inventory probe')
    value=native_inventory_probe_proof(probe_result,probe['envelope'],probe['before'])
    after=worker.bridge.read();witness=checked['witness']
    if (not _scope(after,worker) or not _released(after)
            or exact_side(value['client']) != exact_side(value['server'])
            or quantities(after['inventory'])[0] != quantities(witness['inventory'])[0]
            or not empty_menu(value['client']) or not empty_menu(value['server'])
            or value['client'].get('quickcraft_status') != 0 or value['server'].get('quickcraft_status') != 0
            or math.dist(before['pos'],after['pos']) > .25):
        raise Paused('Source handoff fresh stock, cursor or position changed; preserve both plans')
    # Stock is the fresh operator handback observation, not the earlier 23-dirt
    # admission template. Old SDK commits prove their own history only.
    source=checked['baseline']
    derived=copy.deepcopy(checkpoint)
    absent=world.reconciled_absent_owned
    variants=world.observed_owned_variants
    station_changes=world.reconciled_stations
    for observed in absent:derived['owned'].pop(observed['key'])
    for observed in variants:derived['owned'][observed['key']]=observed['actual']
    for station in station_changes:
        if station['current'] is None:derived['stations'].pop(station['name'])
        else:derived['stations'][station['name']]=list(station['current'])
    if absent or variants or station_changes:
        # The immutable source checkpoint remains the historical ownership
        # record. Missing current walls are never represented as placed.
        protected={tuple(p) for p in derived.get('excluded',[])}
        house=derived.get('small_shelter')
        if house:protected.update(tuple(p) for key in ('layout','floor') for p in house[key])
        protected.update(tuple(station['previous']) for station in station_changes)
        derived['excluded']=[list(p) for p in sorted(protected)]
        derived['reconciled_absent_owned']=copy.deepcopy(absent)
        derived['observed_owned_variants']=copy.deepcopy(variants)
        derived['reconciled_stations']=copy.deepcopy(station_changes)
    checked['derived_checkpoint']=derived
    return {'schema':1,'source':'fresh_kit_physical_baseline','request_id':manifest['id'],
        'newbaseline_id':'baseline-'+uuid.uuid4().hex,**{k:after[k] for k in ('world_id','world_session','dimension','control_revision')},
        'trial_id':worker.registry['trial_id'],'run_id':worker.run_id,'observed_at':after['time'],
        'inventory':copy.deepcopy(after['inventory']),'menu':copy.deepcopy(after['menu']),'position':list(after['pos']),
        'terrain':terrain,'scan_bounds':bounds,'review':copy.deepcopy(source['review']),
        'historical_effects_unresolved':True,'legacy_pending':copy.deepcopy(worker.legacy_pending),
        'forbidden_request_ids':[row['id'] for row in worker.legacy_pending],
        'inventory_review_verified_ids':list(source['inventory_review_verified_ids']),
        'old_action_replayed':False,'old_action_completed':False,
        'current_owned':copy.deepcopy(derived['owned']),'reconciled_absent_owned':copy.deepcopy(absent),
        'observed_owned_variants':copy.deepcopy(variants),
        'current_stations':copy.deepcopy(derived['stations']),'reconciled_stations':copy.deepcopy(station_changes),
        'source_handoff':{'kind':KIND,'manifest_ref':checked['reference'],'source_baseline_ref':manifest['baseline'],
            'source_checkpoint_ref':manifest['checkpoint'],'source_run_id':manifest['source_run_id'],
            'source_parent_pid':manifest['source_parent_pid'],'target_run_id':worker.run_id,
            'stock_fresh':True,'player_work_fresh':True,'source_authorization_inherited':True}}


def claim_handoff(worker, checked, baseline):
    manifest=checked['manifest'];folder=worker.output/'source-material-handoff-claims';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(manifest['id']+'.json')
    value={'schema':1,'handoff_id':manifest['id'],'manifest_sha256':checked['reference']['sha256'],
           'run_id':worker.run_id,'world_session':worker.bridge.session,'baseline_id':baseline['newbaseline_id'],
           'historical_effects_unresolved':True,'old_action_replayed':False,'old_action_completed':False}
    if path.exists() or path.is_symlink(): raise Paused('Source handoff was already claimed; no new automatic material grant')
    if any(p.is_symlink() for p in (folder,*folder.parents)): raise Paused('Source handoff claim directory is linked')
    with path.open('x') as stream:
        json.dump(value,stream,sort_keys=True,allow_nan=False);stream.flush();os.fsync(stream.fileno())
    return value
