"""Fly between bounded surface patches and use the guarded gravel miner.

The miner only opens already exposed, dry gravel. After each patch the player
flies back into open air before another search; it never routes underground
between deposits.
"""

import argparse
import json
import math
import re
import time
from pathlib import Path

from build_supervisor import stocks
from gravel_harvest import WATER_BUFFER,dry_top_gravel, harvest
from fast_descent import descend_if_clear
from material_client import MaterialClient
from shallow_gravel import shallow_candidates,open_and_harvest
from surface_gravel_ledger import SurfaceGravelLedger

GRAVEL = 'minecraft:gravel'


def route_for_targets(value):
    selected = {part.upper() for part in re.split(r'[,;|\s]+', value) if part}
    return 'surface' if selected == {'GRAVEL'} else 'underground'


def candidates(rows, low, high):
    return [entry['pos'] for entry in rows if entry['state'] == 'Block{minecraft:gravel}'
            and all(low[i] <= entry['pos'][i] <= high[i] for i in range(3))
            and dry_top_gravel(rows, entry['pos'])]


def centre(low, high, y):
    return [(low[0] + high[0] + 1)/2, y, (low[2] + high[2] + 1)/2]


def search_tiles(box, height_band):
    x0,z0,x1,z1=box
    if x1<x0 or z1<z0 or x1-x0>128 or z1-z0>128 or height_band[1]-height_band[0]>64:
        raise ValueError('Search box must be ordered and no wider than 129×129')
    xs=list(range(x0,x1+1,16));zs=list(range(z0,z1+1,16))
    if len(xs)*len(zs)>32:raise ValueError('One expedition may search at most 32 surface tiles')
    return [([x,height_band[0],z],[min(x+15,x1),height_band[1],min(z+15,z1)])
            for index,x in enumerate(xs) for z in (zs if index%2==0 else reversed(zs))]


def frontier_tiles(origin, height_band, minimum_radius, maximum_radius, limit, ledger,
                   worksite_anchor=None):
    """Choose unvisited 16×16 tiles in outward square rings around a base."""
    if (minimum_radius < 32 or maximum_radius < minimum_radius or maximum_radius > 512
            or not 1 <= limit <= 32 or height_band[1] - height_band[0] > 64):
        raise ValueError('Invalid bounded surface search frontier')
    base_x=(origin[0]//16)*16;base_z=(origin[1]//16)*16
    chosen=[]
    for radius in range((minimum_radius+15)//16,(maximum_radius+15)//16+1):
        ring = ([(dx,-radius) for dx in range(-radius,radius+1)]
                + [(radius,dz) for dz in range(-radius+1,radius+1)]
                + [(dx,radius) for dx in range(radius-1,-radius-1,-1)]
                + [(-radius,dz) for dz in range(radius-1,-radius,-1)])
        for dx,dz in ring:
            x=base_x+dx*16;z=base_z+dz*16
            low=[x,height_band[0],z];high=[x+15,height_band[1],z+15]
            if worksite_anchor is not None and math.hypot(x+8-worksite_anchor[0],z+8-worksite_anchor[2])>480:
                continue
            if not ledger.covered(low,high,WATER_BUFFER):
                chosen.append((low,high))
                if len(chosen)>=limit:return chosen
    return chosen


def best_surface_layer(dry):
    if not dry:return None
    top=max((p[1] for p in dry),key=lambda y:sum(y-2<=p[1]<=y for p in dry))
    return top-2,top


def expedition(client, regions, target, cruise_y, out, search=False, ledger=None, shallow_depth=0):
    if not 1 <= target <= 64 or not 85 <= cruise_y <= 160 or shallow_depth not in (0,1,2):
        raise ValueError('One guarded expedition collects 1..64 gravel at Y85..160')
    result = {'start': client.status()['pos'], 'gravel_before': stocks(client.status()).get(GRAVEL,0),
              'target': target, 'regions': [], 'skipped_visited': [], 'skipped_out_of_scope': []}
    anchor=getattr(client,'anchor',result['start'])
    reachable=[]
    for low,high in regions:
        site=centre(low,high,cruise_y)
        if math.hypot(site[0]-anchor[0],site[2]-anchor[2])>480:
            result['skipped_out_of_scope'].append([low,high])
        else:
            reachable.append((low,high))
    regions=reachable
    if ledger is not None:
        unvisited=[]
        for low,high in regions:
            if ledger.covered(low,high,WATER_BUFFER):
                result['skipped_visited'].append([low,high])
            else:
                unvisited.append((low,high))
        regions=unvisited
    if regions and client.status()['pos'][1]>cruise_y+40:
        high_site=centre(regions[0][0],regions[0][1],client.status()['pos'][1])
        staging=client.request('navigate',target=high_site,arrival=2,seconds=150)
        if staging.get('phase')!='done':raise RuntimeError('Open-sky survey staging did not complete')
        result['sky_staging']={'pos':client.status()['pos'],
                               'descent':descend_if_clear(client,cruise_y,16)}
    for number, (low, high) in enumerate(regions):
        gained = stocks(client.status()).get(GRAVEL,0) - result['gravel_before']
        if gained >= target: break
        if any(low[i] > high[i] for i in range(3)) or any(high[i]-low[i] > 16 for i in (0,2)) \
                or high[1]-low[1] > (64 if search else 3):
            raise ValueError('Surface survey is too large for one observed tile')
        site = centre(low, high, cruise_y)
        flight = client.request('navigate', target=site, arrival=2, seconds=120)
        if flight.get('phase') != 'done' or client.status()['health'] < 18:
            raise RuntimeError('High approach to surface patch did not complete')
        scan_ceiling=max(high[1]+3,int(cruise_y)+2) if shallow_depth else high[1]+2
        observed = client.request('scan', min=[low[0]-WATER_BUFFER,low[1]-2,low[2]-WATER_BUFFER],
                                  max=[high[0]+WATER_BUFFER,scan_ceiling,high[2]+WATER_BUFFER], details=True)
        dry = candidates(observed['blocks'],low,high)
        shallow=shallow_candidates(observed['blocks'],low,high,shallow_depth,scan_ceiling) if shallow_depth else []
        entry = {'bounds': [low,high], 'high_arrival': client.status()['pos'],
                 'water_buffer_blocks': WATER_BUFFER,
                 'dry_candidates': len(dry),'shallow_candidates':len(shallow),
                 'examples': dry[:8], 'shallow_examples':[v['pos'] for v in shallow[:4]]}
        result['regions'].append(entry)
        if ledger is not None:
            ledger.record(low,high,WATER_BUFFER,'scanned',dry_candidates=len(dry),
                          shallow_candidates=len(shallow),
                          high_arrival=entry['high_arrival'])
        if search and dry:
            y0,y1=best_surface_layer(dry)
            entry['chosen_layer']=[y0,y1]
            dry=[p for p in dry if y0<=p[1]<=y1]
            mine_low=[low[0],y0,low[2]];mine_high=[high[0],y1,high[2]]
        else:
            mine_low,mine_high=low,high
        if dry or shallow:
            try:
                # Cruise to open sky directly above a confirmed surface block,
                # then use the native frame-braked fall. The miner handles only
                # the short final approach, never a 30+ block slow descent.
                now=client.status()['pos']
                if dry:
                    first=min(dry,key=lambda p:(p[0]+.5-now[0])**2+(p[2]+.5-now[2])**2)
                    first_pos=first;surface_y=first[1]
                else:
                    first=min(shallow,key=lambda v:(v['pos'][0]+.5-now[0])**2
                              +(v['pos'][2]+.5-now[2])**2)
                    first_pos=first['pos'];surface_y=first['surface_y']
                above=[first_pos[0]+.5,cruise_y,first_pos[2]+.5]
                staged=client.request('navigate',target=above,arrival=2,seconds=45)
                if staged.get('phase')!='done':raise RuntimeError('High staging above surface gravel failed')
                entry['pre_mine_descent']=descend_if_clear(client,surface_y+5,0)
                region_out = Path(out)/('patch-'+str(number))
                gravel_before=stocks(client.status()).get(GRAVEL,0)
                if dry:
                    entry['harvest'] = harvest(client,mine_low,mine_high,
                                               min(target-gained,len(dry)),region_out)
                else:
                    entry['shallow_harvest']=open_and_harvest(client,first,region_out)
                # Mining stays within one small surface patch. Before searching a
                # different patch, rise to clear air rather than traversing caves.
                climb = client.request('navigate', target=site, arrival=2, seconds=90)
                entry['high_departure'] = {'phase': climb.get('phase'),
                                           'pos': client.status()['pos']}
                if climb.get('phase') != 'done' or client.status()['health'] < 18:
                    raise RuntimeError('Surface patch ascent did not complete')
                remaining_scan=client.request('scan',min=[low[0]-WATER_BUFFER,low[1]-2,low[2]-WATER_BUFFER],
                                              max=[high[0]+WATER_BUFFER,scan_ceiling,high[2]+WATER_BUFFER],details=True)
                remaining_dry=candidates(remaining_scan['blocks'],low,high)
                remaining_shallow=shallow_candidates(remaining_scan['blocks'],low,high,shallow_depth,scan_ceiling) if shallow_depth else []
                entry['remaining_safe']=len(remaining_dry)+len(remaining_shallow)
                if ledger is not None:
                    records=entry.get('harvest',{}).get('blocks',[])
                    unreachable=(dry and not shallow and entry.get('harvest',{}).get('gained')==0
                                 and len(records)>=len(dry)
                                 and all(record.get('approach') for record in records))
                    status='blocked' if unreachable else 'partial' if entry['remaining_safe'] else 'exhausted'
                    ledger.record(low,high,WATER_BUFFER,status,
                                  dry_candidates=len(dry),shallow_candidates=len(shallow),
                                  remaining_safe=entry['remaining_safe'],
                                  **({'retry_after_ms':int(time.time()*1000)+4*60*60*1000} if unreachable else {}),
                                  gravel_gain=stocks(client.status()).get(GRAVEL,0)-gravel_before,
                                  high_departure=entry['high_departure']['pos'])
            except Exception as error:
                if ledger is not None:
                    ledger.record(low,high,WATER_BUFFER,'interrupted',
                                  dry_candidates=len(dry),shallow_candidates=len(shallow),
                                  error=str(error)[:300])
                raise
        elif ledger is not None:
            ledger.record(low,high,WATER_BUFFER,'empty',dry_candidates=0,shallow_candidates=0,
                          high_arrival=entry['high_arrival'])
        Path(out).mkdir(parents=True,exist_ok=True)
        (Path(out)/'progress.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    result['gravel_after'] = stocks(client.status()).get(GRAVEL,0)
    result['gained'] = result['gravel_after']-result['gravel_before']
    result['health'] = client.status()['health']
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region',action='append',nargs=6,type=int,
                        metavar=('MIN_X','MIN_Y','MIN_Z','MAX_X','MAX_Y','MAX_Z'))
    parser.add_argument('--search-box',nargs=4,type=int,
                        metavar=('MIN_X','MIN_Z','MAX_X','MAX_Z'))
    parser.add_argument('--frontier-origin',nargs=2,type=int,metavar=('HOME_X','HOME_Z'))
    parser.add_argument('--min-radius',type=int,default=96)
    parser.add_argument('--max-radius',type=int,default=256)
    parser.add_argument('--max-new-tiles',type=int,default=16)
    parser.add_argument('--height-band',nargs=2,type=int,default=[58,88],
                        metavar=('MIN_Y','MAX_Y'))
    parser.add_argument('--target',type=int,default=32)
    parser.add_argument('--shallow-depth',type=int,choices=(0,1,2),default=0,
                        help='Allow gravel beneath this many natural soil blocks')
    parser.add_argument('--targets',
                        help='Override selected targets for a specific gravel task; otherwise read the Kit mining selection')
    parser.add_argument('--cruise-y',type=float,default=95)
    parser.add_argument('--park-high',type=float,nargs=3,required=True)
    parser.add_argument('--ledger',type=Path,
                        default=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/surface-gravel-visited.json'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    selected=args.targets
    if selected is None:
        config=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit.json')
        selected=json.loads(config.read_text()).get('borerOreTarget','')
    if route_for_targets(selected)!='surface':
        raise ValueError('Mixed ore selections belong to the existing underground miner')
    if sum(bool(choice) for choice in (args.region,args.search_box,args.frontier_origin))!=1:
        raise ValueError('Provide bounded regions, one search box, or one frontier origin')
    client=MaterialClient('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation',args.out,
                          remote_finish='guard',park_target=args.park_high)
    try:
        state=client.status()
        ledger=SurfaceGravelLedger(args.ledger,state['server'],state['dimension'])
        if args.frontier_origin:
            regions=frontier_tiles(args.frontier_origin,args.height_band,args.min_radius,
                                   args.max_radius,args.max_new_tiles,ledger,state['pos'])
        elif args.search_box:
            regions=search_tiles(args.search_box,args.height_band)
        else:
            regions=[(r[:3],r[3:]) for r in args.region]
        result=expedition(client,regions,args.target,args.cruise_y,args.out,
                          search=bool(args.search_box or args.frontier_origin),ledger=ledger,
                          shallow_depth=args.shallow_depth)
        args.out.mkdir(parents=True,exist_ok=True)
        (args.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps({'tiles_scanned':len(result['regions']),
                          'tiles_skipped':len(result['skipped_visited']),
                          'tiles_out_of_scope':len(result['skipped_out_of_scope']),
                          'shallow_candidates':sum(row['shallow_candidates'] for row in result['regions']),
                          'safe_candidates':sum(row['dry_candidates']+row['shallow_candidates'] for row in result['regions']),
                          'gravel_gained':result['gained'],'health':result['health'],
                          'ledger':str(args.ledger),'result':str(args.out/'result.json')},
                         ensure_ascii=False),flush=True)
    finally:client.finish()


if __name__=='__main__':main()
