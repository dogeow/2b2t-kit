"""Fly between bounded surface patches and use the guarded gravel miner.

The miner only opens already exposed, dry gravel. After each patch the player
flies back into open air before another search; it never routes underground
between deposits.
"""

import argparse
import json
import re
import time
from pathlib import Path

from build_supervisor import stocks
from gravel_harvest import WATER_BUFFER,dry_top_gravel, harvest
from fast_descent import descend_if_clear
from material_client import MaterialClient

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
    if x1<x0 or z1<z0 or x1-x0>128 or z1-z0>128 or height_band[1]-height_band[0]>40:
        raise ValueError('Search box must be ordered and no wider than 129×129')
    xs=list(range(x0,x1+1,16));zs=list(range(z0,z1+1,16))
    if len(xs)*len(zs)>32:raise ValueError('One expedition may search at most 32 surface tiles')
    return [([x,height_band[0],z],[min(x+15,x1),height_band[1],min(z+15,z1)])
            for index,x in enumerate(xs) for z in (zs if index%2==0 else reversed(zs))]


def best_surface_layer(dry):
    if not dry:return None
    base=max((p[1] for p in dry),key=lambda y:sum(y<=p[1]<=y+2 for p in dry))
    return base,base+2


def expedition(client, regions, target, cruise_y, out, search=False):
    if not 1 <= target <= 64 or not 85 <= cruise_y <= 160:
        raise ValueError('One guarded expedition collects 1..64 gravel at Y85..160')
    result = {'start': client.status()['pos'], 'gravel_before': stocks(client.status()).get(GRAVEL,0),
              'target': target, 'regions': []}
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
                or high[1]-low[1] > (40 if search else 3):
            raise ValueError('Surface survey is too large for one observed tile')
        site = centre(low, high, cruise_y)
        flight = client.request('navigate', target=site, arrival=2, seconds=120)
        if flight.get('phase') != 'done' or client.status()['health'] < 18:
            raise RuntimeError('High approach to surface patch did not complete')
        observed = client.request('scan', min=[low[0]-WATER_BUFFER,low[1]-2,low[2]-WATER_BUFFER],
                                  max=[high[0]+WATER_BUFFER,high[1]+2,high[2]+WATER_BUFFER], details=True)
        dry = candidates(observed['blocks'],low,high)
        entry = {'bounds': [low,high], 'high_arrival': client.status()['pos'],
                 'water_buffer_blocks': WATER_BUFFER,
                 'dry_candidates': len(dry), 'examples': dry[:8]}
        result['regions'].append(entry)
        if search and dry:
            y0,y1=best_surface_layer(dry)
            entry['chosen_layer']=[y0,y1]
            dry=[p for p in dry if y0<=p[1]<=y1]
            mine_low=[low[0],y0,low[2]];mine_high=[high[0],y1,high[2]]
        else:
            mine_low,mine_high=low,high
        if dry:
            # Cruise to open sky directly above a confirmed surface block,
            # then use the native frame-braked fall. The miner handles only
            # the short final approach, never a 30+ block slow descent.
            now=client.status()['pos']
            first=min(dry,key=lambda p:(p[0]+.5-now[0])**2+(p[2]+.5-now[2])**2)
            above=[first[0]+.5,cruise_y,first[2]+.5]
            staged=client.request('navigate',target=above,arrival=2,seconds=45)
            if staged.get('phase')!='done':raise RuntimeError('High staging above surface gravel failed')
            entry['pre_mine_descent']=descend_if_clear(client,first[1]+5,0)
            region_out = Path(out)/('patch-'+str(number))
            entry['harvest'] = harvest(client,mine_low,mine_high,min(target-gained,len(dry)),region_out)
            # Mining stays within one small surface patch. Before searching a
            # different patch, rise to clear air rather than traversing caves.
            climb = client.request('navigate', target=site, arrival=2, seconds=90)
            entry['high_departure'] = {'phase': climb.get('phase'),
                                       'pos': client.status()['pos']}
            if climb.get('phase') != 'done' or client.status()['health'] < 18:
                raise RuntimeError('Surface patch ascent did not complete')
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
    parser.add_argument('--height-band',nargs=2,type=int,default=[58,88],
                        metavar=('MIN_Y','MAX_Y'))
    parser.add_argument('--target',type=int,default=32)
    parser.add_argument('--targets',
                        help='Override selected targets for a specific gravel task; otherwise read the Kit mining selection')
    parser.add_argument('--cruise-y',type=float,default=95)
    parser.add_argument('--park-high',type=float,nargs=3,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    selected=args.targets
    if selected is None:
        config=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit.json')
        selected=json.loads(config.read_text()).get('borerOreTarget','')
    if route_for_targets(selected)!='surface':
        raise ValueError('Mixed ore selections belong to the existing underground miner')
    if bool(args.region)==bool(args.search_box):
        raise ValueError('Provide either bounded regions or one search box')
    regions=search_tiles(args.search_box,args.height_band) if args.search_box else [(r[:3],r[3:]) for r in args.region]
    client=MaterialClient('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation',args.out,
                          remote_finish='guard',park_target=args.park_high)
    try:
        result=expedition(client,regions,args.target,args.cruise_y,args.out,search=bool(args.search_box))
        args.out.mkdir(parents=True,exist_ok=True)
        (args.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:client.finish()


if __name__=='__main__':main()
