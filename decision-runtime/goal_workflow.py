"""Continuous material/crafting/build phases sharing one native safety lease."""
import json,time,math
from pathlib import Path
from material_client import Handoff
from build_supervisor import stocks
from recipe_catalog import RecipeCatalog
import craft_recipe
from container_hand import select_container_hand
from material_manufacture import manufacture as manufacture_targets

def audit(client,label):
    r=client.request('projection_audit')
    if 'projection_audit' not in r:raise RuntimeError(r.get('detail','Projection audit unavailable'))
    a=r['projection_audit'];(client.out/(label+'.json')).write_text(json.dumps(a,ensure_ascii=False,indent=2))
    print('AUDIT',a['matched'],a['total'],a['kinds'],flush=True);return a

def open_workbench(client,pos,near_depot=None):
    if near_depot:
        inv=stocks(client.status());marker='diamond_sword' if inv.get('minecraft:diamond_sword') else 'diamond_pickaxe'
        r=client.fetch(near_depot,{marker:1})
        if r.get('phase')!='done':raise RuntimeError(r.get('detail'))
    rows=client.request('scan',min=pos,max=pos)['blocks']
    if len(rows)!=1 or rows[0]['state']!='Block{minecraft:crafting_table}':raise RuntimeError('Workbench position changed')
    from work_access import approach_faces
    face=approach_faces(client,pos,rows[0]['state'],('up','north','south','east','west'),seconds=180)
    hand=select_container_hand(client)
    client.checked('interact',pos=pos,face=face,expected_state=rows[0]['state'],expected_hand=hand)
    until=time.monotonic()+5
    while time.monotonic()<until:
        menu=client.status()['menu']
        if menu['type']=='CraftingMenu':
            client.owned_material_menu=menu.get('id');return
        time.sleep(.2)
    raise RuntimeError('Workbench menu was not confirmed')

def craft_targets(client,catalog,targets):
    results=[]
    for output,target in targets:
        if not output.startswith('minecraft:'):output='minecraft:'+output
        s=client.status();before=stocks(s).get(output,0)
        if before>=target:continue
        width=3 if s['menu']['type']=='CraftingMenu' else 2
        plan=catalog.choose(output,stocks(s),width)
        if plan['missing_for_one']:
            results.append({'output':output,'missing':plan['missing_for_one']});print('CRAFT_MISSING',output,plan['missing_for_one'],flush=True);continue
        s=craft_recipe.execute(client,plan,target);after=stocks(s).get(output,0)
        results.append({'output':output,'produced':after-before,'inventory':after,'target':target})
    (client.out/('craft-'+str(int(time.time()*1000))+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2));return results

def subset_matches(observed,targets):
    actual={tuple(row['pos']):row['state'] for row in observed}
    return bool(targets) and all(actual.get(tuple(row['pos']))==row['expected'] for row in targets)

def station_target(label):
    try:
        parts=[int(part.strip()) for part in label.split(',')]
        return [parts[0]+.5,parts[1]+.02,parts[2]+.5] if len(parts)==3 else None
    except (AttributeError,TypeError,ValueError):
        return None

def protected_background(client,state):
    lease=state.get('supervision_lease') or {}
    heartbeat=getattr(client,'heartbeat',None)
    return bool(state.get('material_protocol',0)>=2 and state.get('guard_armed')
                and heartbeat and getattr(heartbeat,'attached',False)
                and lease.get('kind')=='materials' and lease.get('job_session')==getattr(client,'task',None)
                and lease.get('id')==getattr(heartbeat,'id',None)
                and lease.get('world_session')==state.get('world_session')
                and not state.get('manual_movement'))


def verified_build_navigation(anchor,state):
    """Count only native travel with a real pose change, not phase/status churn."""
    job=state.get('build_job') or {}
    station=station_target(job.get('station'))
    old=anchor.get('pos')
    pos=state.get('pos')
    if (not job.get('active') or not job.get('auto_move')
            or job.get('phase') not in ('自动走位','规划走位','打印中')
            or station is None or not isinstance(old,(list,tuple)) or not isinstance(pos,(list,tuple))
            or len(old)!=3 or len(pos)!=3):
        return False
    try:
        moved=math.dist(old,pos)
        closer=math.dist(old,station)-math.dist(pos,station)
    except (TypeError,ValueError):
        return False
    if not math.isfinite(moved) or moved<.5:
        return False
    if closer>=.35:
        return True
    previous=anchor.get('build_job') or {}
    before_path=previous.get('navigation') or {}
    path=job.get('navigation') or {}
    return (path.get('start') is not None and path.get('start')==before_path.get('start')
            and path.get('path_length')==before_path.get('path_length')
            and isinstance(job.get('path_step'),int) and isinstance(previous.get('path_step'),int)
            and job['path_step']>previous['path_step'])


def available_build_material(state):
    """Use the native remaining-item map; never choose an unrelated carried tool."""
    needs=(state.get('build_job')or{}).get('material_needs')or{}
    held=stocks(state)
    candidates=[(min(amount,held.get(item,0)),item)for item,amount in needs.items()
                if isinstance(item,str)and item.startswith('minecraft:')and type(amount)is int
                and amount>0 and held.get(item,0)>0]
    return max(candidates)[1]if candidates else None

def prepare_build_material(client,state):
    item=available_build_material(state)
    if item is None or state.get('hand',{}).get('item')==item and state['hand'].get('count',0)>0:return None
    client.checked('select_item',item=item)
    actual=client.status().get('hand',{})
    if actual.get('item')!=item or actual.get('count',0)<1:
        raise RuntimeError('Actual build material did not reach the held hand; no printer start')
    return item

def build_phase(client,selection_key,seconds=180,stall_seconds=90,complete_cells=None,max_station_repositions=0,background=False,navigation_grace_seconds=15,max_material_refills=32,air_seed_limit=8):
    s=client.status()
    if s['projection_selection'].get('key')!=selection_key:raise Handoff('Selected projection changed')
    if background and not protected_background(client,s):
        raise RuntimeError('Background construction requires the current protected material lease')
    if not s.get('window_active') and not background:
        raise RuntimeError('Minecraft must be the foreground window for construction movement')
    if s['screen']:client.checked('close_menu')
    prepare_build_material(client,client.status())
    client.checked('projection_start',manual_start=True,placement_key=selection_key)
    started=time.monotonic();last_gain=started;last_navigation=None;navigation_anchor=s
    best=0;last_report=-1;last_sample=0;last_subset_check=0;repositions=0;material_refills=0
    while time.monotonic()-started<seconds:
        s=client.status();b=s['build_job']
        if time.monotonic()-last_sample>=2:
            last_sample=time.monotonic()
            with (client.out/'build-station-events.jsonl').open('a') as stream:stream.write(json.dumps({'time':s['time'],'pos':s['pos'],'velocity':s.get('velocity'),'movement_keys':s.get('movement_keys'),'window_active':s.get('window_active'),'flight':s.get('flight'),'health':s['health'],'guard_busy':s.get('guard_busy'),'build':b,'printer':s.get('professional_printer')},ensure_ascii=False)+'\n')
        if b.get('placement_key')!=selection_key or s.get('projection_selection',{}).get('key')!=selection_key:raise Handoff('Projection changed during build')
        if b.get('outcome')=='manual_stop':raise Handoff('Player stopped construction')
        if (background and not protected_background(client,s)) or (not background and not s.get('window_active')):
            if b.get('active'):client.checked('build_control',job_session=b['session'],action='pause_and_report')
            raise RuntimeError('Minecraft left foreground during construction')
        now=time.monotonic()
        if b.get('matched',0)>best:best=b['matched'];last_gain=now
        if verified_build_navigation(navigation_anchor,s):
            last_navigation=now;navigation_anchor=s
        if best-last_report>=10:
            print('BUILD',best,b.get('total'),b.get('phase'),flush=True);last_report=best
            progress=getattr(client,'set_progress',None)
            if callable(progress):progress(done=best,phase='自动放置')
        if not b['active']:break
        printer=s.get('professional_printer',{})
        if (material_refills<max_material_refills and not s.get('guard_busy')
                and not printer.get('waiting_for_server') and printer.get('last_hand_mismatch')
                and available_build_material(s) and s.get('hand',{}).get('count',0)==0):
            # Litematica can leave the hand empty after a full stack. Pause its
            # owned queue before one ordinary inventory swap, validate the real
            # hand, then resume the same complete projection. No placement or
            # success counter is synthesized by the supply action.
            client.checked('build_control',job_session=b['session'],action='pause_and_report')
            fresh=client.status()
            if fresh.get('projection_selection',{}).get('key')!=selection_key:raise Handoff('Projection changed before material refill')
            item=prepare_build_material(client,fresh)
            if item:
                with(client.out/'build-material-refills.jsonl').open('a')as stream:
                    stream.write(json.dumps({'world_session':fresh.get('world_session'),'previous_job_session':b['session'],
                        'item':item,'actual_hand':client.status().get('hand'),'matched_before':best,'placement_credit':0})+'\n')
                client.checked('projection_start',manual_start=True,placement_key=selection_key)
                material_refills+=1;last_gain=time.monotonic();last_navigation=None;navigation_anchor=client.status()
                print('BUILD_ACTUAL_HAND_REFILLED',item,material_refills,flush=True);continue
        if complete_cells and not s.get('guard_busy') and b.get('queue_settled') and not s.get('professional_printer',{}).get('waiting_for_server') and time.monotonic()-last_subset_check>=3:
            last_subset_check=time.monotonic()
            low=[min(row['pos'][i] for row in complete_cells) for i in range(3)]
            high=[max(row['pos'][i] for row in complete_cells) for i in range(3)]
            observed=client.request('scan',min=low,max=high)['blocks']
            fresh=client.status()
            if fresh.get('projection_selection',{}).get('key')!=selection_key:raise Handoff('Projection changed during subset verification')
            settled=fresh.get('build_job',{}).get('queue_settled') and not fresh.get('professional_printer',{}).get('waiting_for_server')
            if settled and subset_matches(observed,complete_cells):
                print('BUILD_SUBSET_VERIFIED',len(complete_cells),flush=True);break
        stalled_for=time.monotonic()-last_gain
        # Walking between stations deserves a brief grace period, but cannot
        # keep an unproductive print job alive indefinitely. The original
        # overall `seconds` cap remains in force as well.
        moving_grace=(last_navigation is not None
                      and stalled_for<=stall_seconds+max(0,navigation_grace_seconds)
                      and time.monotonic()-last_navigation<=8)
        if not s.get('guard_busy') and stalled_for>stall_seconds and not moving_grace:
            target=station_target(b.get('station'))
            if (b.get('phase')=='自动走位' and target and repositions<max_station_repositions
                    and s.get('window_active') and s['health']>=18):
                client.checked('build_control',job_session=b['session'],action='pause_and_report')
                moved=client.request('navigate',target=target,arrival=2,seconds=20)
                proof={'time':s['time'],'station':b['station'],'from':s['pos'],'phase':moved.get('phase'),
                       'detail':moved.get('detail'),'to':client.status()['pos']}
                with (client.out/'build-repositions.jsonl').open('a') as stream:
                    stream.write(json.dumps(proof,ensure_ascii=False)+'\n')
                repositions+=1
                if moved.get('phase')=='done' and client.status()['health']>=18:
                    client.checked('projection_start',manual_start=True,placement_key=selection_key)
                    last_gain=time.monotonic();last_sample=0
                    print('BUILD_REPOSITION',repositions,b['station'],flush=True)
                    continue
            print('BUILD_STALL',b.get('reason'),flush=True);break
        time.sleep(.3)
    s=client.status();b=s['build_job']
    if b['active']:
        from build_pause_reconciliation import pause_or_observe_completion
        pause_or_observe_completion(client,b['session'])
    result=audit(client,'after-build-'+str(int(time.time())))
    if air_seed_limit and client.status().get('projection_air_seed_axis_protocol')==1:
        from projection_air_finish import finish_carried
        def checkpoint():
            q=client.status()
            if q.get('projection_selection',{}).get('key')!=selection_key:raise Handoff('Projection changed before air finish')
            if (background and not protected_background(client,q))or(not background and not q.get('window_active')):
                raise Handoff('Construction control changed before air finish')
            return q
        completed=finish_carried(client,result,client.out/('air-finish-'+str(time.time_ns())),checkpoint,air_seed_limit)
        if completed:
            print('BUILD_METEOR_AIR_FINISHED',len(completed),flush=True)
            result=audit(client,'after-air-finish-'+str(int(time.time())))
    return result
