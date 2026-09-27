"""Use the native bounded AREA engine for dry sand, one verified box at a time."""
import argparse
import json
import math
import time
from pathlib import Path

from material_client import MaterialClient
from material_trip_policy import carried,room_for_item,trip_complete
from surface_sand_harvest import SAND,SAND_STATE,validate_region,scan_bounds,safe_state
from drop_collection import collect_drop

ROOT=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation')


def recover_quarry_drops(client,low,high):
    attempted=set();before=carried(client.status(),SAND)
    for _ in range(24):
        state=client.status();safe_state(state)
        drops=[e for e in state.get('entities',[]) if e.get('type')=='minecraft:item'
            and e.get('stack',{}).get('item')==SAND and e.get('uuid') not in attempted
            and len(e.get('pos',[]))==3
            and all(low[i]-3<=e['pos'][i]<=high[i]+3 for i in range(3))]
        if not drops:break
        drop=min(drops,key=lambda e:sum((a-b)**2 for a,b in zip(e['pos'],state['pos'])))
        attempted.add(drop['uuid'])
        collect_drop(client,drop,observation=state,seconds=25)
    return {'attempted':len(attempted),'recovered':carried(client.status(),SAND)-before}


def choose_quarry(rows,low,high,player):
    cells={tuple(v['pos']):v for v in rows}
    sand_y=[p[1] for p,v in cells.items() if v['state']==SAND_STATE
            and all(low[i]<=p[i]<=high[i] for i in range(3))]
    if not sand_y:return None
    top=max(sand_y)
    best=None;best_score=None
    for bottom in range(max(64,low[1],top-11),top):
        inside={};buffer={};counts={}
        for x in range(low[0]-3,high[0]+4):
            for z in range(low[2]-3,high[2]+4):
                column=[cells.get((x,y,z)) for y in range(bottom,top+1)]
                support=cells.get((x,bottom-1,z),{})
                inside[x,z]=(all(v is None or v['state']==SAND_STATE for v in column)
                    and support.get('solid',False) and not support.get('fluid',False)
                    and all((x,y,z) not in cells for y in (top+1,top+2)))
                counts[x,z]=sum(v is not None and v['state']==SAND_STATE for v in column)
                buffer[x,z]=all(not (v:=cells.get((x,y,z))) or
                    not v.get('fluid',False) and not v.get('block_entity',False)
                    for y in range(bottom-2,top+3))
        for width in (16,12,8,6,4,2):
            for x in range(low[0],high[0]-width+2):
                for z in range(low[2],high[2]-width+2):
                    if not all(inside[xx,zz] for xx in range(x,x+width) for zz in range(z,z+width)):continue
                    if not all(buffer[xx,zz] for xx in range(x-3,x+width+3) for zz in range(z-3,z+width+3)):continue
                    count=sum(counts[xx,zz] for xx in range(x,x+width) for zz in range(z,z+width))
                    if not count:continue
                    score=(count,-math.hypot(x+width/2-player[0],z+width/2-player[2]),-width)
                    if best_score is None or score>best_score:
                        actual_top=max(y for xx in range(x,x+width) for zz in range(z,z+width)
                                       for y in range(bottom,top+1) if cells.get((xx,y,zz),{}).get('state')==SAND_STATE)
                        best_score=score;best={'min':[x,bottom,z],'max':[x+width-1,max(bottom+1,actual_top),z+width-1],'sand':count}
    return best


def preparation_target(pos,choice,rows):
    """Only gain the clearance required by the verified box and local footing."""
    required=choice['max'][1]+2
    if pos[1]>=required:return None
    nearby=[row['pos'][1]+1 for row in rows
            if abs(row['pos'][0]+.5-pos[0])<=1.3 and abs(row['pos'][2]+.5-pos[2])<=1.3
            and not row.get('passable',False)]
    # The cruise arrival radius is at least one block; preserve >= 2 actual
    # blocks above the quarry even if it stops at the near edge of that radius.
    height=max(required+1.1,max(nearby,default=pos[1]-1)+2.25)
    return [pos[0],height,pos[2]]


def run(client,low,high,target,out):
    validate_region(low,high);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    report={'before':carried(client.status(),SAND),'target':target,'batches':[]}
    start=time.monotonic()
    while not trip_complete(client.status(),SAND,target):
        state=client.status();safe_state(state)
        scan_min,scan_max=scan_bounds(low,high)
        rows=client.request('scan',min=scan_min,max=scan_max,details=True)['blocks']
        choice=choose_quarry(rows,low,high,state['pos'])
        if choice is None:
            report['reason']='No more dry sand-only boxes in this region';break
        amount=min(choice['sand'],target-carried(state,SAND),room_for_item(state,SAND),1024)
        shovels=[v for v in state['inventory'] if v.get('slot',99)<36
            and v.get('item') in ('minecraft:diamond_shovel','minecraft:netherite_shovel')
            and v.get('durability',0)>=min(amount,256)+32]
        if not shovels:raise RuntimeError('Durable sand shovel required before the next native batch')
        tool=max(shovels,key=lambda v:v['durability'])
        if state.get('selected_slot')!=tool['slot']:
            client.checked('select_item',item=tool['item'],slot=tool['slot'])
        preparation=preparation_target(client.status()['pos'],choice,rows)
        if preparation is not None:
            client.checked('navigate',target=preparation,arrival=.2,seconds=15)
        before=carried(client.status(),SAND);began=time.monotonic()
        result=client.request('quarry_batch',min=choice['min'],max=choice['max'],item=SAND,
                              target_count=amount,seconds=min(600,max(60,amount*3)))
        pickup=recover_quarry_drops(client,choice['min'],choice['max'])
        after=client.status();entry={**choice,'requested':amount,'before':before,
            'after':carried(after,SAND),'gained':carried(after,SAND)-before,
            'phase':result.get('phase'),'detail':result.get('detail'),
            'seconds':round(time.monotonic()-began,2),'health':after['health'],'drop_cleanup':pickup}
        if result.get('phase')!='done':
            check=client.request('scan',min=choice['min'],max=choice['max'],details=True)['blocks']
            entry['sand_blocks_remaining']=sum(row['state']==SAND_STATE for row in check)
            entry['region_complete']=entry['sand_blocks_remaining']==0 and not after.get('borer_active')
        report['batches'].append(entry);report['after']=carried(after,SAND)
        (out/'progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('BATCH',json.dumps(entry,ensure_ascii=False),flush=True)
        if result.get('phase')!='done' and not entry.get('region_complete'):
            report['reason']='Native batch stopped; inspect actual world before resuming';break
        if entry['gained']<=0:
            report['reason']='No inventory progress in the completed batch';break
    report.update(after=carried(client.status(),SAND),seconds=round(time.monotonic()-start,2),
                  target_reached=carried(client.status(),SAND)>=target,
                  bag_full=room_for_item(client.status(),SAND)==0)
    (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def select_region(client,regions,target,out):
    """Let Jev rank freshly verified dry quarry alternatives, never raw coordinates."""
    if not 1<=len(regions)<=10:raise ValueError('Provide 1..10 bounded regions')
    available={};options={'wait':'Keep protection and wait; no offered dry quarry is suitable.'}
    for name,(low,high) in regions.items():
        validate_region(low,high);lo,hi=scan_bounds(low,high)
        reply=client.request('scan',min=lo,max=hi,details=True)
        if 'blocks' not in reply:continue
        choice=choose_quarry(reply['blocks'],low,high,client.status()['pos'])
        if choice:
            available[name]=choice
            options[name]=f"Mine a verified dry supported sand-only box with {choice['sand']} sand, from {choice['min']} to {choice['max']}."
    if not available:return None,None
    decision=client.advise('Gather the remaining raw sand before crafting or building. Choose an efficient safe batch; avoid depleted fragments.',options,
                           {'remaining_sand':max(0,target-carried(client.status(),SAND)),'verified_regions':available})
    (Path(out)/'region-decision.json').write_text(json.dumps({'decision':decision,'candidates':available},ensure_ascii=False,indent=2))
    key=decision['choice']
    return (key,decision) if key in available else (None,decision)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--region',nargs=6,type=int,action='append',required=True,help='Repeat for Jev selection among verified dry regions')
    p.add_argument('--target-carried',type=int,required=True)
    p.add_argument('--park-high',nargs=3,type=float,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();regions={f'region_{i+1}':(r[:3],r[3:]) for i,r in enumerate(args.region)}
    if not 1<=args.target_carried<=2304:raise ValueError('Target must fit an ordinary backpack')
    for low,high in regions.values():validate_region(low,high)
    client=MaterialClient(ROOT,args.out,remote_finish='guard',park_target=args.park_high)
    try:
        state=client.status()
        if state.get('quarry_protocol',0)<1 and state.get('kit_version')!='1.9.97':
            raise RuntimeError('Native quarry interface requires quarry_protocol 1')
        decision=None
        if len(regions)>1:
            selected,decision=select_region(client,regions,args.target_carried,args.out)
            if selected is None:
                print('No quarry selected; keeping guarded finish',flush=True);return
            low,high=regions[selected]
        else:low,high=next(iter(regions.values()))
        result=run(client,low,high,args.target_carried,args.out)
        if decision:client.record_advice_outcome(decision,'sand_trip_finished',before=result['before'],after=result['after'],target_reached=result['target_reached'])
        print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:client.finish()


if __name__=='__main__':main()
