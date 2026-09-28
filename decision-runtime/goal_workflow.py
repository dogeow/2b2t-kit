"""Continuous material/crafting/build phases sharing one native safety lease."""
import json,time,math
from pathlib import Path
from material_client import Handoff
from build_supervisor import stocks
from recipe_catalog import RecipeCatalog
import craft_recipe
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
    client.checked('approach_block',pos=pos,face='up',expected_state=rows[0]['state'],seconds=180)
    client.checked('select_item',item='minecraft:diamond_sword')
    client.checked('interact',pos=pos,face='up',expected_state=rows[0]['state'],expected_hand='minecraft:diamond_sword')
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


def build_phase(client,selection_key,seconds=180,stall_seconds=90,complete_cells=None,max_station_repositions=0,background=False,navigation_grace_seconds=15):
    s=client.status()
    if s['projection_selection'].get('key')!=selection_key:raise Handoff('Selected projection changed')
    if background and not protected_background(client,s):
        raise RuntimeError('Background construction requires the current protected material lease')
    if not s.get('window_active') and not background:
        raise RuntimeError('Minecraft must be the foreground window for construction movement')
    if s['screen']:client.checked('close_menu')
    client.checked('projection_start',manual_start=True,placement_key=selection_key)
    started=time.monotonic();last_gain=started;last_navigation=None;navigation_anchor=s
    best=0;last_report=-1;last_sample=0;last_subset_check=0;repositions=0
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
    if b['active']:client.checked('build_control',job_session=b['session'],action='pause_and_report')
    return audit(client,'after-build-'+str(int(time.time())))
