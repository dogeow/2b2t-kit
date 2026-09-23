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

def build_phase(client,selection_key,seconds=180,stall_seconds=90,complete_cells=None,max_station_repositions=0):
    s=client.status()
    if s['projection_selection'].get('key')!=selection_key:raise Handoff('Selected projection changed')
    if not s.get('window_active'):
        raise RuntimeError('Minecraft must be the foreground window for construction movement')
    if s['screen']:client.checked('close_menu')
    client.checked('projection_start',manual_start=True,placement_key=selection_key)
    started=time.monotonic();last_gain=started;best=0;last_report=-1;last_sample=0;last_subset_check=0;repositions=0
    while time.monotonic()-started<seconds:
        s=client.status();b=s['build_job']
        if time.monotonic()-last_sample>=2:
            last_sample=time.monotonic()
            with (client.out/'build-station-events.jsonl').open('a') as stream:stream.write(json.dumps({'time':s['time'],'pos':s['pos'],'velocity':s.get('velocity'),'movement_keys':s.get('movement_keys'),'window_active':s.get('window_active'),'flight':s.get('flight'),'health':s['health'],'guard_busy':s.get('guard_busy'),'build':b,'printer':s.get('professional_printer')},ensure_ascii=False)+'\n')
        if b.get('placement_key')!=selection_key or s.get('projection_selection',{}).get('key')!=selection_key:raise Handoff('Projection changed during build')
        if b.get('outcome')=='manual_stop':raise Handoff('Player stopped construction')
        if not s.get('window_active'):
            if b.get('active'):client.checked('build_control',job_session=b['session'],action='pause_and_report')
            raise RuntimeError('Minecraft left foreground during construction')
        if b.get('matched',0)>best:best=b['matched'];last_gain=time.monotonic()
        if best-last_report>=10:print('BUILD',best,b.get('total'),b.get('phase'),flush=True);last_report=best
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
        if not s.get('guard_busy') and time.monotonic()-last_gain>stall_seconds:
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
