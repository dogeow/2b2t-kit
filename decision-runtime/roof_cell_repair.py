"""Finite correction of exposed wrong double slabs using one existing Kit owner.

Keeps valid upper structures and all historical reservations. Each correction
recovers both dropped slabs before an exact model printer placement. Pending
requests are journaled and never retried by this runner.
"""
from pathlib import Path
import math,time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from roof_double_slab_plan import DOUBLE,clear_route
from roof_slab_window_plan import SLAB
from goal_workflow import build_phase


def options(expected,rows,player,*,low,high,protected=(),y=72):
    fenced=set(map(tuple,protected));result=[]
    neighbors=[(0,0,0),(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    for p,state in expected.items():
        row=rows.get(p,{})
        if (p[1]!=y or state!=SLAB or row.get('state')!=DOUBLE
                or row.get('fluid')is not False or row.get('block_entity')is not False
                or any(tuple(p[i]+d[i]for i in range(3))in fenced for d in neighbors)):continue
        pose=[p[0]+.5,y+1.15,p[2]+.5]
        # An upper model pillar is preserved; a later plan can dismantle/restore
        # it explicitly rather than trying to fly or mine through it.
        approach=[pose[0],min(y+9.15,high[1]-2.),pose[2]]
        if approach[1]>=y+2.15 and clear_route(pose,approach,rows,low=low,high=high):
            result.append({'target':list(p),'hover':pose,'distance':math.dist(player,pose)})
    return sorted(result,key=lambda v:v['distance'])


def run(builder,model,out,*,low,high,protected,allowed_at,limit=8,y=72):
    if type(limit)is not int or not 1<=limit<=16:raise ValueError('Finite one to sixteen corrections required')
    out=Path(out);out.mkdir(exist_ok=False);path=out/'progress.json';world=builder.check()['world_session']
    expected={tuple(v['pos']):v['state']for v in model['expected']};key=model['placement_key'];book={'complete':False,'cells':[],'pending':None,'world_session':world,'old_requests_replayed':False,'full_tower_complete':False}
    def save():write_json(path,book)
    def n(op,**kw):
        book['pending']={'op':op,'params':kw};save();r=builder.n(op,**kw);book['pending']=None;save();return r
    def scan(details=True):
        builder.check();r=n('scan',min=low,max=high,details=details)
        if (r.get('world_session')!=world or r.get('scan_start_revision')!=r.get('scan_end_revision')
                or r.get('scan_cells_read')!=math.prod(b-a+1 for a,b in zip(low,high))
                or r.get('scan_cells_read')!=r.get('scan_total_cells')):raise RuntimeError('Complete current-world roof scan required')
        observed={tuple(v['pos']):v for v in r['blocks']}
        if not(out/'first-scene.json').exists():write_json(out/'first-scene.json',r)
        write_json(out/'latest-scene.json',r)
        book['latest_roof_counts']={'matching_bottom':sum(expected.get(p)==SLAB and v['state']==SLAB for p,v in observed.items()if p[1]==y),'matching_double':sum(expected.get(p)==DOUBLE and v['state']==DOUBLE for p,v in observed.items()if p[1]==y),'scan_id':r['id']if 'id'in r else None,'scan_time':r.get('time'),'world_session':world}
        save()
        return r,observed
    save()
    try:
        for index in range(limit):
            scene,rows=scan();choices=options(expected,rows,builder.check()['pos'],low=low,high=high,protected=protected,y=y)
            if not choices:book['stopped_reason']='no_exposed_unprotected_wrong_double';break
            chosen=next((v for v in choices if allowed_at(v['target'],v['hover'])),None)
            if chosen is None:book['stopped_reason']='current_threats_not_separated';break
            target=chosen['target'];pose=chosen['hover'];cell={'target':target,'hover':pose,'complete':False,'removal_attempted':False};book['cells'].append(cell);folder=out/f'cell-{index:02d}';folder.mkdir();write_json(folder/'before-scene.json',scene);save()
            a=builder.check()
            if clear_route(a['pos'],pose,rows,low=low,high=high):cell['direct_observed_route']=True;n('navigate',target=pose,arrival=.1,air_only=True,seconds=40)
            else:
                height=max(y+33.2,a['pos'][1]);n('navigate',target=[a['pos'][0],height,a['pos'][2]],arrival=.1,air_only=True,seconds=40);n('navigate',target=[pose[0],height,pose[2]],arrival=.1,air_only=True,seconds=40);n('navigate',target=pose,arrival=.1,air_only=True,seconds=40)
            before=inventory_counts(builder.check())['minecraft:cobblestone_slab'];cell['stock_before']=before;n('select_item',item='minecraft:diamond_pickaxe');r=n('scan',min=target,max=target,details=True)
            if len(r['blocks'])!=1 or r['blocks'][0]['state']!=DOUBLE:raise RuntimeError('Repair target changed; no mining input')
            cell['removal_attempted']=True;save();r=n('mine_block',pos=target,face='up',expected_state=DOUBLE,seconds=15)
            if not(r.get('server_confirmed')is True and r.get('native_sequence',0)>0 and r.get('native_sequence')==r.get('server_ack_sequence')):raise RuntimeError('Original mining not acknowledged; never remine')
            cell['mining_ack']={k:r.get(k)for k in ['id','native_sequence','server_ack_sequence','server_confirmed']};save();r=n('scan',min=target,max=target,details=True)
            if r['blocks']:raise RuntimeError('Original removed roof cell is occupied; no repeat')
            deadline=time.monotonic()+8
            while inventory_counts(builder.check())['minecraft:cobblestone_slab']!=before+2:
                if time.monotonic()>deadline:raise RuntimeError('Known mined slabs not both collected; retain hole, no remine')
                time.sleep(.1)
            cell['verified_recovered']=2;save();n('navigate',target=[pose[0],y+2.15,pose[2]],arrival=.1,air_only=True,seconds=30);n('select_item',item='minecraft:cobblestone_slab');n('projection_batch_set',placement_key=key,positions=[target],min_feet_y=y+2);cell['replacement_started']=True;save()
            cell['native_result']=build_phase(builder.client,key,seconds=45,stall_seconds=20,complete_cells=[{'pos':target,'expected':SLAB}],background=True,max_station_repositions=0,max_material_refills=0,air_seed_limit=0);save()
            frames=[]
            for _ in range(2):
                frame,observed_rows=scan(False);observed={p:v['state']for p,v in observed_rows.items()};original={p:v['state']for p,v in rows.items()}
                if observed.get(tuple(target))!=SLAB or {p for p in original.keys()|observed.keys()if original.get(p)!=observed.get(p)}!={tuple(target)}:raise RuntimeError('Repair or surrounding blocks differ; retain original actions')
                if inventory_counts(frame)['minecraft:cobblestone_slab']!=before+1:raise RuntimeError('Recovery/placement stock balance unproved')
                frames.append(frame);time.sleep(.12)
            printer=builder.check().get('professional_printer')or{}
            if (printer.get('owned')is not False or printer.get('travel_pending')!=0
                    or printer.get('waiting_for_server')is not False or printer.get('failure')!=''):
                raise RuntimeError('Printer still has an unsettled input; retain original receipt')
            cell.update(complete=True,stock_after=before+1,net_recovered=1,other_observed_blocks_unchanged=True);write_json(folder/'after-scene.json',frames[-1]);write_json(folder/'result.json',cell);save();n('projection_batch_clear',placement_key=key)
        book.update(complete=True,verified_repairs=sum(v['complete']for v in book['cells']),health=builder.check()['health']);save();return book
    except BaseException as error:
        book['error']=repr(error);save();raise
