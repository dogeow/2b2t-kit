"""Kit-only reconnaissance for dry, sealed gravel from surface to depth 20."""

import argparse
import json
import math
from pathlib import Path

from deep_gravel_survey import deep_candidates,terrain_summary
from gravel_harvest import WATER_BUFFER
from material_client import MaterialClient
from surface_gravel_expedition import frontier_tiles, centre
from surface_gravel_ledger import SurfaceGravelLedger

ROOT='/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation'
# The previous ledger's empty tiles were produced by exact-state matching,
# which missed grass_block[snowy=false]. Keep that history but resurvey it.
DEFAULT_LEDGER=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/deep-gravel-visited-0-20-v2.json')


def survey(client,regions,ledger,out,cruise_y=150,min_vein_blocks=16):
    report={'start':client.status()['pos'],'regions':[]}
    for low,high in regions:
        actual_low=[low[0],30,low[2]]
        actual_high=[high[0],152,high[2]]
        if ledger.covered(actual_low,actual_high,WATER_BUFFER):continue
        target=centre(actual_low,actual_high,cruise_y)
        if math.hypot(target[0]-client.anchor[0],target[2]-client.anchor[2])>480:
            report['regions'].append({'bounds':[actual_low,actual_high],'skipped':'worksite limit'})
            continue
        moved=client.request('navigate',target=target,arrival=2,seconds=120)
        if moved.get('phase')!='done' or client.status()['health']<18:
            raise RuntimeError('High survey waypoint was not reached safely')
        chunks=[]
        for y0,y1 in ((30,120),(121,152)):
            scanned=client.request('scan',
                                   min=[actual_low[0]-WATER_BUFFER,y0,actual_low[2]-WATER_BUFFER],
                                   max=[actual_high[0]+WATER_BUFFER,y1,actual_high[2]+WATER_BUFFER],
                                   details=True)
            if 'blocks' not in scanned:
                raise RuntimeError(scanned.get('detail','Deep survey unavailable'))
            chunks.extend(scanned['blocks'])
        found=deep_candidates(chunks,actual_low,actual_high,0,20)
        ranked=sorted(found,key=lambda row:(-row['observed_component_size'],row['depth']))
        entry={'bounds':[actual_low,actual_high],'high_arrival':client.status()['pos'],
               'blocks_observed':len(chunks),'deep_candidates':len(found),
               'largest_observed_vein':max((row['observed_component_size'] for row in found),default=0),
               'terrain':terrain_summary(chunks,actual_low,actual_high),
               'examples':ranked[:3]}
        report['regions'].append(entry)
        ledger.record(actual_low,actual_high,WATER_BUFFER,'partial' if found else 'empty',
                      deep_candidates=len(found),survey_depth=[0,20],survey_policy_version=2,
                      terrain=entry['terrain'],
                      high_arrival=entry['high_arrival'])
        Path(out).mkdir(parents=True,exist_ok=True)
        (Path(out)/'progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        if entry['largest_observed_vein']>=min_vein_blocks:break
    report['health']=client.status()['health']
    report['best_observed_vein']=max((entry.get('largest_observed_vein',0)
                                      for entry in report['regions']),default=0)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',nargs=2,type=int,required=True)
    parser.add_argument('--min-radius',type=int,default=32)
    parser.add_argument('--max-radius',type=int,default=256)
    parser.add_argument('--max-new-tiles',type=int,default=16)
    parser.add_argument('--cruise-y',type=float,default=150)
    parser.add_argument('--min-vein-blocks',type=int,default=16)
    parser.add_argument('--park-high',nargs=3,type=float,required=True)
    parser.add_argument('--ledger',type=Path,default=DEFAULT_LEDGER)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if not 1<=args.min_vein_blocks<=512:parser.error('--min-vein-blocks must be 1..512')
    client=MaterialClient(ROOT,args.out,remote_finish='guard',park_target=args.park_high)
    try:
        state=client.status()
        ledger=SurfaceGravelLedger(args.ledger,state['server'],state['dimension'])
        # The route planner uses a compact height band. Every tile is then
        # scanned in two vertical bands through Y152 within the native 50k-cell limit.
        regions=frontier_tiles(args.origin,[30,94],args.min_radius,args.max_radius,
                               args.max_new_tiles,ledger,state['pos'])
        result=survey(client,regions,ledger,args.out,args.cruise_y,args.min_vein_blocks)
        args.out.mkdir(parents=True,exist_ok=True)
        (args.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps({'tiles_scanned':len(result['regions']),
                          'deep_candidates':sum(x.get('deep_candidates',0) for x in result['regions']),
                          'best_observed_vein':result['best_observed_vein'],
                          'health':result['health'],'result':str(args.out/'result.json')},
                         ensure_ascii=False),flush=True)
    finally:client.finish()


if __name__=='__main__':main()
