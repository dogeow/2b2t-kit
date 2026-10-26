"""Finish only unreserved double cells via explicit, unreserved model supports.

This placement-only loop keeps every old pending target and support fenced.
Each normal use gets its own saved receipt and two distinct state/stock frames.
"""
from pathlib import Path
import math,time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from roof_double_slab_plan import choices,clear_route,DOUBLE,SLAB
from goal_workflow import build_phase
TOP=SLAB.replace("type=bottom","type=top")


def run(builder,model,out,*,low,high,protected,limit=8,y=72):
    if type(limit)is not int or not 1<=limit<=16:raise ValueError('Finite one to sixteen targets required')
    out=Path(out);out.mkdir(exist_ok=False);file=out/'progress.json';expected={tuple(v['pos']):v['state']for v in model['expected']};blocked=set(map(tuple,protected));world=builder.check()['world_session'];book={'complete':False,'cells':[],'pending':None,'world_session':world,'old_requests_replayed':False,'mining_sent':False,'full_tower_complete':False}
    def save():write_json(file,book)
    def n(op,**params):
        book['pending']={'op':op,'params':params};save();r=builder.n(op,**params);book['pending']=None;save();return r
    def scene(details):
        r=n('scan',min=low,max=high,details=details)
        if r.get('world_session')!=world or r.get('scan_cells_read')!=r.get('scan_total_cells')or r['scan_total_cells']!=math.prod(b-a+1 for a,b in zip(low,high))or r.get('scan_start_revision')!=r.get('scan_end_revision'):raise RuntimeError('Complete current-world scene required')
        return r,{tuple(v['pos']):v for v in r['blocks']}
    save()
    try:
        for index in range(limit):
            before_scene,rows=scene(True);write_json(out/'latest-scene.json',before_scene);available=choices(expected,rows,builder.check()['pos'],low=low,high=high,protected=blocked,y=y)
            for pos,wanted in expected.items():
                if pos[1]!=y or wanted!=DOUBLE or pos in blocked or rows.get(pos,{}).get('state')!=TOP or rows[pos].get('fluid')is not False or rows[pos].get('block_entity')is not False:continue
                pose=[pos[0]+.5,y+2.1,pos[2]+.5];upper=[pose[0],min(y+9.15,high[1]-2.),pose[2]]
                if clear_route(pose,upper,rows,low=low,high=high):available.append({'target':list(pos),'hover':pose,'stages':[],'item_cost':1,'native_top_merge':True,'distance':math.dist(builder.check()['pos'],pose)})
            if not available:book['stopped_reason']='no_unreserved_visible_double_plan';break
            stock=inventory_counts(builder.check())['minecraft:cobblestone_slab'];chosen=next((v for v in available if v['item_cost']<=stock),None)
            if chosen is None:book['stopped_reason']='insufficient_actual_slabs';break
            target=chosen['target'];pose=chosen['hover'];cell={'target':target,'plan':chosen,'complete':False,'placement_attempted':False,'stages':[],'stock_before':stock};book['cells'].append(cell);folder=out/f'cell-{index:02d}';folder.mkdir();write_json(folder/'before-scene.json',before_scene);save();a=builder.check()
            if clear_route(a['pos'],pose,rows,low=low,high=high):cell['direct_observed_route']=True;n('navigate',target=pose,arrival=.1,air_only=True,seconds=40)
            else:
                h=max(y+12.1,a['pos'][1]);n('navigate',target=[a['pos'][0],h,a['pos'][2]],arrival=.1,air_only=True,seconds=40);n('navigate',target=[pose[0],h,pose[2]],arrival=.1,air_only=True,seconds=40);n('navigate',target=pose,arrival=.1,air_only=True,seconds=40)
            native_top_merge=chosen.get('native_top_merge',False)
            for number,stage in enumerate(chosen['stages']):
                assert tuple(target)not in blocked and tuple(stage['support'])not in blocked
                n('select_item',item='minecraft:cobblestone_slab');current=n('scan',min=target,max=target,details=True);actual=current['blocks'][0]['state']if current['blocks']else'Block{minecraft:air}'
                if actual!=stage['expected_before']:raise RuntimeError('Current stage changed before input; no replay')
                if stage['support']!=target:
                    anchor=n('scan',min=stage['support'],max=stage['support'],details=True)
                    if len(anchor['blocks'])!=1 or anchor['blocks'][0]['state']!=stage['expected_support']:raise RuntimeError('Exact model support changed before input')
                if math.dist(builder.check()['pos'],pose)>.4:raise RuntimeError('Owned pose changed before interaction')
                cell['placement_attempted']=True;cell['pending_stage']=stage;save();reply=n('interact',pos=stage['support'],face=stage['face'],expected_state=stage['expected_support'],expected_hand='minecraft:cobblestone_slab');cell['pending_stage_request']=reply['id'];save();deadline=time.monotonic()+5;frames=[];observed_after=None;allowed={stage['expected_after']}
                if number==0 and stage['expected_before']=='Block{minecraft:air}'and stage['expected_support']==DOUBLE:allowed.add(TOP)
                while len(frames)<2:
                    f=n('scan',min=target,max=target,details=False)
                    if len(f['blocks'])==1 and f['blocks'][0]['state']in allowed and inventory_counts(f)['minecraft:cobblestone_slab']==stock-number-1 and(not frames or f['time']>frames[-1]):
                        if observed_after is not None and observed_after!=f['blocks'][0]['state']:raise RuntimeError('Intermediate slab changed during confirmation')
                        observed_after=f['blocks'][0]['state'];frames.append(f['time'])
                    if time.monotonic()>deadline:raise RuntimeError('Original normal use not confirmed; retain it without replay')
                    time.sleep(.1)
                cell['stages'].append({'id':reply['id'],'expected_after':stage['expected_after'],'observed_after':observed_after,'confirmation_times':frames});cell.pop('pending_stage',None);cell.pop('pending_stage_request',None);save()
                if observed_after==TOP:native_top_merge=True;break
            if native_top_merge:
                neighbour=n('scan',min=[target[0]-1,y,target[2]-1],max=[target[0]+1,y,target[2]+1],details=True)
                if any(tuple(v['pos'])in blocked and v['state']not in (SLAB,TOP)for v in neighbour['blocks']):raise RuntimeError('Protected full or interactive support beside top merge; no native merge started')
                n('select_item',item='minecraft:cobblestone_slab');n('projection_batch_set',placement_key=model['placement_key'],positions=[target],min_feet_y=y+2);cell['placement_attempted']=True;book['pending']={'op':'native_top_merge','target':target};save();cell['native_top_merge']=build_phase(builder.client,model['placement_key'],seconds=45,stall_seconds=20,complete_cells=[{'pos':target,'expected':DOUBLE}],background=True,max_station_repositions=0,max_material_refills=0,air_seed_limit=0);book['pending']=None;save();printer=builder.check().get('professional_printer')or{}
                if (printer.get('owned')is not False or printer.get('waiting_for_server')is not False or printer.get('travel_pending')!=0 or printer.get('failure')!=''or printer.get('server_confirmed')!=1 or(printer.get('last_proposal')or{}).get('ack_final')is not True or(printer.get('last_proposal')or{}).get('ack_actual')!=DOUBLE or(printer.get('last_proposal')or{}).get('target')!=', '.join(map(str,target))):raise RuntimeError('Native top merge has not independently acknowledged its one use')
                cell['native_top_ack']=printer;n('projection_batch_clear',placement_key=model['placement_key']);save()
            for _ in range(2):
                f,after=scene(False);original={p:v['state']for p,v in rows.items()};actual={p:v['state']for p,v in after.items()}
                if actual.get(tuple(target))!=DOUBLE or {p for p in original.keys()|actual.keys()if original.get(p)!=actual.get(p)}!={tuple(target)}:raise RuntimeError('Target or protected surroundings changed unexpectedly')
                if inventory_counts(f)['minecraft:cobblestone_slab']!=stock-chosen['item_cost']:raise RuntimeError('Normal-use slab balance differs')
                time.sleep(.1)
            cell.update(complete=True,stock_after=stock-chosen['item_cost'],surrounding_blocks_unchanged=True);write_json(folder/'after-scene.json',f);write_json(folder/'result.json',cell);save();write_json(out/'latest-scene.json',f)
        book.update(complete=True,verified_repairs=sum(v['complete']for v in book['cells']),health=builder.check()['health']);save();return book
    except BaseException as error:book['error']=repr(error);save();raise
